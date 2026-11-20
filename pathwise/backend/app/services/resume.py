import hashlib
import io
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import HTTPException, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    CandidateCertification, CandidateEducation, CandidateExperience, CandidateProfile, CandidateProject, CandidateSkill,
    Resume, ResumeExtraction,
)
from app.services.matching import level_from_years
from app.services.skills import canonical, get_index

logger = logging.getLogger("pathwise.resume")

ALLOWED = {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
SECTION_NAMES = {
    "skills": r"(technical |core |key |professional )?(skills|competenc(y|ies)|technologies|tech stack|tools)( & technologies| and technologies)?",
    "education": r"(education|academic( background| qualifications)?|qualifications|education and training)",
    "experience": r"((professional |work |employment |relevant )?(experience|history)|employment|work history|career history|internships?)",
    "projects": r"((personal |academic |key |selected |notable )?projects|portfolio)",
    "certifications": r"(certifications?|certificates?|licenses?( & certifications)?|courses|training|achievements & certifications)",
    "summary": r"(summary|professional summary|profile|objective|career objective|about me|about)",
    "other": r"(languages|interests|hobbies|references|awards|honors|publications|volunteer(ing)?( experience)?|activities)",
}
DEGREES = (
    ("phd", r"\b(ph\.?\s?d\.?|doctorate|doctor of philosophy)\b"),
    ("master", r"\b(master'?s?|m\.?\s?sc\.?|m\.?\s?s\.?(?=\s|,|\(|$)|mba|m\.?\s?eng\.?|m\.?\s?tech\.?|ms\s?cs|mphil|m\.?\s?phil)\b"),
    ("bachelor", r"\b(bachelor'?s?|b\.?\s?sc\.?|b\.?\s?s\.?(?=\s|,|\(|$)|b\.?\s?e\.?(?=\s|,|\(|$)|b\.?\s?tech\.?|bba|bca|bs\s?cs|undergraduate|b\.?\s?a\.?(?=\s|,|\(|$)|bscs)\b"),
    ("diploma", r"\b(diploma|associate degree|associate of|a\.?a\.?s\.?|dae)\b"),
    ("high_school", r"\b(intermediate|high school|secondary school|a-levels?|matric(ulation)?|hssc|fsc|f\.?sc\.?|ssc|12th|higher secondary|o-levels?|fa/fsc|pre-engineering|ics)\b"),
)
INSTITUTION = re.compile(r"(university|college|institute|school|academy|polytechnic|campus|iqra|fast|nust|comsats)", re.I)
DATE_RANGE = re.compile(
    r"(?P<sm>(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+)?(?P<sy>(?:19|20)\d{2})\s*(?:-|–|—|to|until)\s*(?:(?P<present>present|current|now|ongoing|today)|(?P<em>(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+)?(?P<ey>(?:19|20)\d{2}))",
    re.I,
)
MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
ISO_MONTH = re.compile(r"\b((?:19|20)\d{2})[-/.](0[1-9]|1[0-2])(?!\d)")
SLASH_MONTH = re.compile(r"(?<![\d/])(0?[1-9]|1[0-2])[/.]((?:19|20)\d{2})\b")
EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<!\d)(\+?\d[\d\s().\-]{8,16}\d)(?!\d)")
BULLET = re.compile(r"^\s*[•●▪■\-\*•·▪►➢]+\s*")


def validate_upload(filename: str, content: bytes):
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED:
        raise HTTPException(400, "Only PDF and DOCX files are accepted")
    if not content:
        raise HTTPException(400, "The uploaded file is empty")
    if len(content) > settings.max_resume_bytes:
        raise HTTPException(413, f"File is too large. The maximum size is {settings.max_resume_bytes // (1024 * 1024)} MB")
    if ext == ".pdf" and not content.startswith(b"%PDF"):
        raise HTTPException(400, "This file is not a valid PDF")
    if ext == ".docx" and not content.startswith(b"PK"):
        raise HTTPException(400, "This file is not a valid DOCX document")
    return ext


def save_resume(db: Session, profile: CandidateProfile, upload: UploadFile, content: bytes) -> Resume:
    ext = validate_upload(upload.filename, content)
    folder = Path(settings.storage_dir) / "resumes" / str(profile.id)
    folder.mkdir(parents=True, exist_ok=True)
    stored = folder / f"{uuid.uuid4().hex}{ext}"
    stored.write_bytes(content)
    stored.chmod(0o600)
    for old in db.scalars(select(Resume).where(Resume.candidate_id == profile.id, Resume.is_active.is_(True))):
        old.is_active = False
    safe_name = re.sub(r"[^\w.\- ]", "_", Path(upload.filename).name)[:200]
    resume = Resume(candidate_id=profile.id, original_filename=safe_name, stored_path=str(stored), mime_type=ALLOWED[ext], size_bytes=len(content), sha256=hashlib.sha256(content).hexdigest(), status="uploaded")
    db.add(resume)
    db.commit()
    return resume


def extract_text(path: str, mime: str) -> str:
    if mime == ALLOWED[".pdf"]:
        from pypdf import PdfReader

        reader = PdfReader(path)
        if reader.is_encrypted:
            try:
                if not reader.decrypt(""):
                    raise ValueError("The PDF is password protected")
            except Exception:
                raise ValueError("The PDF is password protected")
        pages = [(page.extract_text() or "") for page in reader.pages[:15]]
        text = "\n".join(pages)
    else:
        from docx import Document

        document = Document(path)
        lines = [p.text for p in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                seen = []
                for cell in row.cells:
                    if cell.text not in seen:
                        seen.append(cell.text)
                lines.append(" | ".join(seen))
        text = "\n".join(lines)
    text = text.replace("\x00", "").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def heading_of(line: str) -> str | None:
    stripped = re.sub(r"[:\-–—_=*#\s]+$", "", line.strip())
    stripped = re.sub(r"^[#*\s]+", "", stripped)
    if not stripped or len(stripped) > 45:
        return None
    for name, pattern in SECTION_NAMES.items():
        if re.fullmatch(pattern, stripped, re.I):
            return name
    return None


def split_sections(text: str) -> tuple[list[str], dict[str, list[str]]]:
    lines = [l.rstrip() for l in text.split("\n")]
    header, sections, current = [], {}, None
    for line in lines:
        name = heading_of(line)
        if name:
            current = name
            sections.setdefault(current, [])
            continue
        if current is None:
            header.append(line)
        else:
            sections[current].append(line)
    return header, sections


def normalize_numeric_dates(line: str) -> str:
    line = ISO_MONTH.sub(lambda m: f"{MONTH_ABBR[int(m.group(2)) - 1]} {m.group(1)}", line)
    return SLASH_MONTH.sub(lambda m: f"{MONTH_ABBR[int(m.group(1)) - 1]} {m.group(2)}", line)


def months_between(sy, sm, ey, em):
    start = (sy * 12) + (MONTHS.get((sm or "jan")[:3].lower(), 1) - 1)
    end = (ey * 12) + (MONTHS.get((em or "dec")[:3].lower(), 12) - 1)
    return max(0, end - start + 1), start, end


def parse_experience(lines: list[str]) -> list[dict]:
    now = datetime.now(timezone.utc)
    entries, current = [], None
    previous = ""
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        original = line
        line = normalize_numeric_dates(line)
        match = DATE_RANGE.search(line)
        if match:
            sy = int(match.group("sy"))
            if match.group("present"):
                ey, em = now.year, MONTHS[["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"][now.month - 1]] and ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"][now.month - 1]
            else:
                ey, em = int(match.group("ey")), match.group("em")
            months, start, end = months_between(sy, match.group("sm"), ey, em)
            if months == 0 or sy > now.year + 1:
                continue
            before = BULLET.sub("", line[: match.start()].strip(" |,-–—•()·\t"))
            after = line[match.end():].strip(" |,-–—•()·\t")
            trailing = ""
            if len(before) >= 3 and re.search(r"[.!?]\s", after + " ") and len(after) > 25:
                head, trailing = before, after
            else:
                head = BULLET.sub("", (before + " " + after).strip(" |,-–—•()·\t"))
            if len(head) < 3 and previous:
                head = previous
                entry_evidence = f"{previous} {original}"
            else:
                entry_evidence = original
            title, company = split_title_company(head)
            current = {"title": title, "company": company, "start": f"{sy}-{MONTHS.get((match.group('sm') or 'jan')[:3].lower(), 1):02d}", "end": "present" if match.group("present") else f"{ey}-{MONTHS.get((em or 'dec')[:3].lower(), 12):02d}", "months": months, "_range": (start, end), "description": [], "evidence": entry_evidence[:240]}
            if trailing:
                current["description"].append(trailing)
            entries.append(current)
        elif current is not None and (BULLET.match(raw) or len(line) > 40):
            current["description"].append(BULLET.sub("", line))
        else:
            previous = line
            if current is not None and len(line) <= 60 and not BULLET.match(raw):
                current = current
    return entries


def split_title_company(head: str) -> tuple[str, str | None]:
    for sep in (" at ", " @ ", " | ", " - ", " – ", " — ", ", "):
        if sep in head:
            left, right = head.split(sep, 1)
            if left.strip() and right.strip():
                return left.strip()[:200], right.strip()[:200]
    return head.strip()[:200], None


def total_years(entries: list[dict]) -> float:
    ranges = sorted(e["_range"] for e in entries)
    merged = []
    for start, end in ranges:
        if merged and start <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return round(sum(e - s + 1 for s, e in merged) / 12, 1)


def institution_name(value: str | None) -> str | None:
    if not value:
        return None
    value = BULLET.sub("", value)
    for part in re.split(r"\s[-–—|]\s|,|\|", value):
        if INSTITUTION.search(part):
            return part.strip()[:200]
    return None


def parse_education(lines: list[str], full_text: str) -> list[dict]:
    pool = [l.strip() for l in lines if l.strip()] or [l.strip() for l in full_text.split("\n") if re.search(r"\b(bachelor|master|ph\.?d|diploma|b\.?sc|m\.?sc|degree|university|intermediate)\b", l, re.I)]
    found, seen = [], set()
    for i, line in enumerate(pool):
        if DATE_RANGE.search(line) and not any(re.search(p, line, re.I) for _, p in DEGREES) and not INSTITUTION.search(line):
            continue
        level = None
        for name, pattern in DEGREES:
            if re.search(pattern, line, re.I):
                level = name
                break
        if level is None:
            continue
        context = " ".join(pool[max(0, i - 1): i + 2])
        institution = next((l for l in (line, *(pool[j] for j in (i - 1, i + 1) if 0 <= j < len(pool))) if INSTITUTION.search(l)), None)
        years = re.findall(r"(?:19|20)\d{2}", context)
        key = (level, re.sub(r"\W+", "", line.lower())[:40])
        if key in seen:
            continue
        seen.add(key)
        found.append({"degree": BULLET.sub("", line)[:200], "level": level, "institution": institution_name(institution), "year": int(years[-1]) if years else None, "evidence": line[:240]})
    return found[:8]


def parse_list_section(lines: list[str], limit=15) -> list[dict]:
    items = []
    for raw in lines:
        line = BULLET.sub("", raw.strip())
        if len(line) < 3 or heading_of(line):
            continue
        items.append({"name": re.sub(r"\s+", " ", line)[:200], "evidence": raw.strip()[:240]})
    return items[:limit]


def parse_projects(lines: list[str]) -> list[dict]:
    projects, current = [], None
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        is_bullet = bool(BULLET.match(raw))
        text = BULLET.sub("", line)
        title_like = len(text) <= 80 and not text.endswith(".") and not is_bullet
        if title_like or (is_bullet and not current and re.search(r"[:–—-]\s", text)):
            name = re.split(r"\s[:–—-]\s|:\s", text, 1)[0][:120]
            current = {"name": name, "description": [text] if is_bullet else [], "evidence": line[:240]}
            projects.append(current)
        elif current is not None:
            current["description"].append(text)
        else:
            current = {"name": re.split(r"\s[:–—-]\s|:\s", text, 1)[0][:120], "description": [text], "evidence": line[:240]}
            projects.append(current)
    return [{"name": p["name"], "description": " ".join(p["description"])[:600] or None, "evidence": p["evidence"]} for p in projects[:12]]


def parse_header(header: list[str], text: str) -> dict:
    nonempty = [l.strip() for l in header if l.strip()][:10]
    name = None
    for line in nonempty[:5]:
        words = line.split()
        if 2 <= len(words) <= 4 and all(re.fullmatch(r"[A-Za-z][A-Za-z.'\-]*", w) for w in words) and not heading_of(line):
            name = line
            break
    email = EMAIL.search(text)
    phone = None
    for m in PHONE.finditer("\n".join(nonempty) or text[:600]):
        digits = re.sub(r"\D", "", m.group(1))
        if 9 <= len(digits) <= 15 and not re.fullmatch(r"(?:19|20)\d{2}\D*(?:19|20)\d{2}", m.group(1)):
            phone = m.group(1).strip()
            break
    location = None
    for line in nonempty:
        for token in re.split(r"[|•·▪]|\s{2,}", line):
            token = token.strip()
            if re.fullmatch(r"[A-Z][A-Za-z.\s]+,\s*[A-Z][A-Za-z.\s]+", token) and "@" not in token and len(token) < 50:
                location = token
                break
        if location:
            break
    from app.services.nlp import header_entities, is_person

    entities = header_entities(nonempty)
    if entities["person"] and (name is None or not is_person(name)):
        name = entities["person"]
    location = location or entities["place"]
    return {"name": name, "email": email.group(0) if email else None, "phone": phone, "location": location}


def parse_resume_text(db: Session, text: str) -> dict:
    header, sections = split_sections(text)
    index = get_index(db)
    found = index.find(text)
    skills = [{"skill": v["skill"], "evidence": v["evidence"], "mentions": v["count"]} for v in found.values() if v["kind"] == "technical"]
    soft = [{"skill": v["skill"], "evidence": v["evidence"], "mentions": v["count"]} for v in found.values() if v["kind"] == "soft"]
    skills.sort(key=lambda s: -s["mentions"])
    experience = parse_experience(sections.get("experience", []))
    years = total_years(experience) if experience else None
    if years is None:
        m = re.search(r"(\d{1,2})\+?\s*years?\s+of\s+(?:professional\s+)?experience", text, re.I)
        years = float(m.group(1)) if m else 0.0
    education = parse_education(sections.get("education", []), text)
    certs = parse_list_section(sections.get("certifications", []))
    seen = {c["name"].lower() for c in certs}
    for line in text.split("\n"):
        if re.search(r"\b(certified|certification|certificate)\b", line, re.I) and len(line.strip()) < 140 and BULLET.sub("", line.strip()).lower() not in seen and heading_of(line) is None:
            certs.append({"name": BULLET.sub("", line.strip()), "evidence": line.strip()[:240]})
            seen.add(BULLET.sub("", line.strip()).lower())
    projects = parse_projects(sections.get("projects", []))
    info = parse_header(header, text)
    for e in experience:
        e["description"] = " ".join(e["description"])[:1200]
    return {
        "name": info["name"], "email": info["email"], "phone": info["phone"], "location": info["location"],
        "skills": skills, "soft_skills": soft, "years_experience": years, "experience_level": level_from_years(years),
        "education": education, "experience": [{k: v for k, v in e.items() if k != "_range"} for e in experience],
        "projects": projects, "certifications": certs[:12], "summary": " ".join(l.strip() for l in sections.get("summary", []) if l.strip())[:1200] or None,
    }


def llm_enrich(text: str, parsed: dict) -> dict | None:
    if not (settings.llm_extraction_enabled and settings.anthropic_api_key):
        return None
    prompt = (
        "Extract ONLY facts that literally appear in this resume. Do not infer or invent anything. "
        'Return JSON with keys: "skills" (list of strings), "certifications" (list), "projects" (list), "job_titles" (list).\n\nRESUME:\n' + text[:12000]
    )
    try:
        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": settings.llm_model, "max_tokens": 1500, "messages": [{"role": "user", "content": prompt}]},
            timeout=40,
        )
        response.raise_for_status()
        import json as _json

        raw = response.json()["content"][0]["text"]
        data = _json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    except Exception as error:
        logger.warning("LLM enrichment skipped: %s", str(error)[:150])
        return None
    lowered = text.lower()
    verified = {}
    for key in ("skills", "certifications", "projects", "job_titles"):
        verified[key] = [v for v in data.get(key, []) if isinstance(v, str) and 2 < len(v) < 120 and v.lower() in lowered]
    return verified


def apply_extraction(db: Session, profile: CandidateProfile, parsed: dict):
    cid = profile.id
    for model in (CandidateEducation, CandidateExperience):
        db.execute(delete(model).where(model.candidate_id == cid))
    for model in (CandidateCertification, CandidateProject):
        db.execute(delete(model).where(model.candidate_id == cid, model.source == "resume"))
    db.execute(delete(CandidateSkill).where(CandidateSkill.candidate_id == cid, CandidateSkill.source == "resume"))
    db.flush()
    manual = {canonical(s.skill) for s in db.scalars(select(CandidateSkill).where(CandidateSkill.candidate_id == cid))}
    for item in parsed["skills"]:
        if canonical(item["skill"]) not in manual:
            db.add(CandidateSkill(candidate_id=cid, skill=item["skill"], kind="technical", source="resume", evidence=item["evidence"]))
            manual.add(canonical(item["skill"]))
    for item in parsed["soft_skills"]:
        if canonical(item["skill"]) not in manual:
            db.add(CandidateSkill(candidate_id=cid, skill=item["skill"], kind="soft", source="resume", evidence=item["evidence"]))
            manual.add(canonical(item["skill"]))
    for e in parsed["education"]:
        db.add(CandidateEducation(candidate_id=cid, degree=e["degree"], level=e["level"], institution=e["institution"], end_year=e["year"]))
    for e in parsed["experience"]:
        db.add(CandidateExperience(candidate_id=cid, title=e["title"], company=e["company"], description=e["description"], start_date=e["start"], end_date=e["end"], months=e["months"]))
    for c in parsed["certifications"]:
        db.add(CandidateCertification(candidate_id=cid, name=c["name"], source="resume", evidence=c["evidence"]))
    for p in parsed["projects"]:
        db.add(CandidateProject(candidate_id=cid, name=p["name"], description=p["description"], source="resume", evidence=p["evidence"]))
    profile.years_experience = parsed["years_experience"]
    profile.experience_level = parsed["experience_level"]
    if not profile.location and parsed.get("location"):
        profile.location = parsed["location"]
    if not profile.phone and parsed.get("phone"):
        profile.phone = parsed["phone"][:40]
    if not profile.summary and parsed.get("summary"):
        profile.summary = parsed["summary"]
    profile.updated_at = datetime.now(timezone.utc)


def process_resume(db: Session, resume_id: int) -> Resume | None:
    resume = db.get(Resume, resume_id)
    if resume is None or resume.status in ("processed",):
        return resume
    profile = db.get(CandidateProfile, resume.candidate_id)
    resume.status = "processing"
    db.commit()
    try:
        text = extract_text(resume.stored_path, resume.mime_type)
        if len(text) < 80:
            raise ValueError("We could not read any text from this file. Scanned or image-only CVs are not supported; please upload a text-based PDF or DOCX")
        parsed = parse_resume_text(db, text)
        method = "rules"
        if profile.ai_processing_consent:
            extra = llm_enrich(text, parsed)
            if extra:
                have = {canonical(s["skill"]) for s in parsed["skills"]}
                index = get_index(db)
                for skill in extra["skills"]:
                    entry = index.by_name.get(canonical(skill))
                    if entry and entry[1] == "technical" and canonical(skill) not in have:
                        parsed["skills"].append({"skill": entry[0], "evidence": next((l.strip()[:240] for l in text.split("\n") if skill.lower() in l.lower()), None), "mentions": 1})
                have_c = {c["name"].lower() for c in parsed["certifications"]}
                for cert in extra["certifications"]:
                    if cert.lower() not in have_c:
                        parsed["certifications"].append({"name": cert, "evidence": next((l.strip()[:240] for l in text.split("\n") if cert.lower() in l.lower()), None)})
                method = "rules+llm"
        existing = db.scalar(select(ResumeExtraction).where(ResumeExtraction.resume_id == resume.id))
        evidence = {"skills": {s["skill"]: s["evidence"] for s in parsed["skills"]}, "education": {e["degree"]: e["evidence"] for e in parsed["education"]}, "certifications": {c["name"]: c["evidence"] for c in parsed["certifications"]}}
        if existing is None:
            existing = ResumeExtraction(resume_id=resume.id)
            db.add(existing)
        existing.raw_text, existing.structured, existing.evidence, existing.method, existing.error = text, parsed, evidence, method, None
        existing.confirmed_by_candidate = False
        if resume.is_active:
            apply_extraction(db, profile, parsed)
        resume.status, resume.error = "processed", None
        resume.processed_at = datetime.now(timezone.utc)
    except Exception as error:
        db.rollback()
        resume = db.get(Resume, resume_id)
        resume.status = "failed"
        resume.error = str(error)[:480] if isinstance(error, ValueError) else "This file could not be processed. Please check that it is a valid, text-based PDF or DOCX."
        logger.warning("resume %s failed: %s", resume_id, error)
    db.commit()
    return resume


def process_pending(db: Session, limit: int = 5) -> int:
    ids = db.scalars(select(Resume.id).where(Resume.status == "uploaded").order_by(Resume.id).limit(limit)).all()
    for rid in ids:
        process_resume(db, rid)
    return len(ids)
