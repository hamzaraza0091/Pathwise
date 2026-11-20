import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants import DEFAULT_WEIGHTS, EXPERIENCE_LEVELS, LEVEL_YEARS
from app.models import (
    CandidateCertification, CandidateEducation, CandidateExperience, CandidatePreference, CandidateProfile,
    CandidateProject, CandidateSkill, Job, MatchingExplanation, MatchingModelVersion, MatchScore, Resume,
)
from app.services import embeddings
from app.services.normalize import aware, education_rank
from app.services.skills import canonical, related_to

DISCLAIMER = "This percentage estimates how well your profile fits the job description. It is not the probability of being interviewed or hired."
STOP = {"a", "an", "the", "and", "or", "of", "for", "in", "at", "to", "with", "remote", "senior", "junior", "sr", "jr", "lead", "intern", "ii", "iii", "i"}
TITLE_SYNONYMS = {"developer": "engineer", "dev": "engineer", "programmer": "engineer", "swe": "engineer", "frontend": "frontend", "front": "frontend", "backend": "backend", "back": "backend", "ml": "machine", "ai": "machine", "fullstack": "fullstack", "full": "fullstack"}
WORLDWIDE = {"worldwide", "anywhere", "global", "remote", "all", "international", "earth", "any", "everywhere"}


@dataclass
class CandidateSnapshot:
    skills: dict[str, str] = field(default_factory=dict)
    years: float = 0.0
    level: str | None = None
    education_level: int = 0
    has_education: bool = False
    titles: list[str] = field(default_factory=list)
    desired_titles: list[str] = field(default_factory=list)
    location: str = ""
    work_modes: list[str] = field(default_factory=list)
    employment_types: list[str] = field(default_factory=list)
    preferred_locations: list[str] = field(default_factory=list)
    min_salary: float | None = None
    salary_currency: str | None = None
    relocation: bool = False
    text: str = ""
    has_profile_data: bool = False

    def signature(self) -> str:
        payload = json.dumps({
            "s": sorted(self.skills), "y": round(self.years, 1), "l": self.level, "e": self.education_level, "t": sorted(self.titles),
            "dt": sorted(self.desired_titles), "loc": self.location, "wm": sorted(self.work_modes), "et": sorted(self.employment_types),
            "pl": sorted(self.preferred_locations), "ms": self.min_salary, "r": self.relocation, "tx": hashlib.md5(self.text.encode()).hexdigest(),
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass
class JobSnapshot:
    id: int | None
    title: str
    description: str
    required: list[str]
    preferred: list[str]
    min_years: float | None
    level: str | None
    education_required: str | None
    location: str | None
    work_mode: str | None
    employment_type: str | None
    salary_min: float | None
    salary_max: float | None
    salary_currency: str | None
    embedding: bytes | None = None
    embedding_model: str | None = None


def title_tokens(value: str) -> set[str]:
    words = re.findall(r"[a-z0-9+#]+", (value or "").lower())
    return {TITLE_SYNONYMS.get(w, w) for w in words if w not in STOP and len(w) > 1}


def title_overlap(job_title: str, candidate_titles: list[str]) -> float | None:
    job = title_tokens(job_title)
    if not job or not candidate_titles:
        return None
    best = 0.0
    for title in candidate_titles:
        tokens = title_tokens(title)
        if tokens:
            best = max(best, len(job & tokens) / len(job))
    return best


def build_candidate_snapshot(db: Session, profile: CandidateProfile) -> CandidateSnapshot:
    cid = profile.id
    skills = {canonical(s.skill): s.skill for s in db.scalars(select(CandidateSkill).where(CandidateSkill.candidate_id == cid, CandidateSkill.kind == "technical"))}
    experience = db.scalars(select(CandidateExperience).where(CandidateExperience.candidate_id == cid)).all()
    education = db.scalars(select(CandidateEducation).where(CandidateEducation.candidate_id == cid)).all()
    prefs = db.scalar(select(CandidatePreference).where(CandidatePreference.candidate_id == cid))
    projects = db.scalars(select(CandidateProject).where(CandidateProject.candidate_id == cid)).all()
    certs = db.scalars(select(CandidateCertification).where(CandidateCertification.candidate_id == cid)).all()
    exp_years = sum((e.months or 0) for e in experience) / 12
    years = profile.years_experience if profile.years_experience is not None else exp_years
    level = profile.experience_level
    if level is None and (experience or profile.years_experience is not None):
        level = level_from_years(years)
    titles = [e.title for e in experience if e.title]
    if profile.headline:
        titles.append(profile.headline)
    resume = db.scalar(select(Resume).where(Resume.candidate_id == cid, Resume.is_active.is_(True)).order_by(Resume.id.desc()))
    raw_text = resume.extraction.raw_text if resume and resume.extraction and resume.extraction.raw_text else ""
    pieces = [profile.headline or "", profile.summary or "", " ".join(skills.values()), " ".join(e.title + " " + (e.description or "") for e in experience),
              " ".join(p.name + " " + (p.description or "") for p in projects), " ".join(c.name for c in certs)]
    text = "\n".join(p for p in pieces if p).strip() or raw_text[:3000]
    if raw_text and len(text) < 400:
        text = f"{text}\n{raw_text[:3000]}"
    snapshot = CandidateSnapshot(
        skills=skills, years=float(years or 0), level=level,
        education_level=max([education_rank(e.level) for e in education], default=0), has_education=bool(education),
        titles=titles, location=profile.location or "", text=text,
        has_profile_data=bool(skills or experience or profile.summary or profile.headline),
    )
    if prefs:
        snapshot.desired_titles = list(prefs.desired_titles or [])
        snapshot.work_modes = list(prefs.work_modes or [])
        snapshot.employment_types = list(prefs.employment_types or [])
        snapshot.preferred_locations = list(prefs.preferred_locations or [])
        snapshot.min_salary = prefs.min_salary
        snapshot.salary_currency = prefs.salary_currency
        snapshot.relocation = bool(prefs.open_to_relocation)
    return snapshot


def level_from_years(years: float) -> str:
    for level in EXPERIENCE_LEVELS:
        low, high = LEVEL_YEARS[level]
        if low <= years < high:
            return level
    return "Executive"


def build_job_snapshot(job: Job) -> JobSnapshot:
    return JobSnapshot(
        id=job.id, title=job.title, description=job.description or "",
        required=[s.skill for s in job.skills if s.is_required], preferred=[s.skill for s in job.skills if not s.is_required],
        min_years=job.min_years, level=job.experience_level, education_required=job.education_required, location=job.location,
        work_mode=job.work_mode, employment_type=job.employment_type, salary_min=job.salary_min, salary_max=job.salary_max,
        salary_currency=job.salary_currency, embedding=job.embedding, embedding_model=job.embedding_model,
    )


def skill_coverage(candidate: dict[str, str], wanted: list[str]):
    matched, related, missing = [], [], []
    for skill in wanted:
        canon = canonical(skill)
        if canon in candidate:
            matched.append(skill)
        elif any(related_to(canon, own) for own in candidate):
            related.append(skill)
        else:
            missing.append(skill)
    coverage = (len(matched) + 0.5 * len(related)) / len(wanted) if wanted else None
    return matched, related, missing, coverage


def score_skills(c: CandidateSnapshot, j: JobSnapshot):
    req_m, req_r, req_x, req_cov = skill_coverage(c.skills, j.required)
    pre_m, pre_r, pre_x, pre_cov = skill_coverage(c.skills, j.preferred)
    if req_cov is not None and pre_cov is not None:
        score = 100 * (0.8 * req_cov + 0.2 * pre_cov)
    elif req_cov is not None:
        score = 100 * req_cov
    elif pre_cov is not None:
        score = 100 * pre_cov
    else:
        score = None
    detail = {"matched_required": req_m, "related_required": req_r, "missing_required": req_x, "matched_preferred": pre_m, "related_preferred": pre_r, "missing_preferred": pre_x}
    return score, detail


def score_experience(c: CandidateSnapshot, j: JobSnapshot):
    parts, weights, notes = [], [], {}
    required = j.min_years
    if required is None and j.level in LEVEL_YEARS:
        required = float(LEVEL_YEARS[j.level][0])
    if required is not None:
        if required <= 0:
            years_score = 100.0
        else:
            years_score = min(100.0, 100 * c.years / required)
        if j.level in ("Entry Level", "Junior") and c.years > LEVEL_YEARS.get(j.level, (0, 2))[1] + 4:
            years_score = min(years_score, 85.0)
        parts.append(years_score)
        weights.append(0.5)
    notes.update({"candidate_years": round(c.years, 1), "required_years": required})
    overlap = title_overlap(j.title, [*c.titles, *c.desired_titles])
    if overlap is not None:
        parts.append(100 * overlap)
        weights.append(0.3)
    if j.level in EXPERIENCE_LEVELS and c.level in EXPERIENCE_LEVELS:
        gap = abs(EXPERIENCE_LEVELS.index(j.level) - EXPERIENCE_LEVELS.index(c.level))
        parts.append({0: 100.0, 1: 75.0, 2: 45.0}.get(gap, 20.0))
        weights.append(0.2)
    notes.update({"candidate_level": c.level, "job_level": j.level, "title_overlap": None if overlap is None else round(overlap, 2)})
    if not parts:
        return None, notes
    return sum(p * w for p, w in zip(parts, weights)) / sum(weights), notes


def score_education(c: CandidateSnapshot, j: JobSnapshot):
    if not j.education_required:
        return None, {"required": None, "candidate_highest": c.education_level}
    need = education_rank(j.education_required)
    if not c.has_education:
        return 50.0, {"required": j.education_required, "note": "No education on your profile"}
    gap = need - c.education_level
    score = 100.0 if gap <= 0 else {1: 65.0, 2: 35.0}.get(gap, 10.0)
    return score, {"required": j.education_required, "candidate_highest": c.education_level}


def loc_tokens(value: str | None) -> set[str]:
    return {t for t in re.findall(r"[a-z]+", (value or "").lower()) if len(t) > 2}


def score_location(c: CandidateSnapshot, j: JobSnapshot):
    job_tokens = loc_tokens(j.location)
    cand_tokens = loc_tokens(c.location)
    if j.work_mode == "remote":
        restricted = bool(job_tokens) and not (job_tokens & WORLDWIDE)
        if restricted and cand_tokens and not (job_tokens & cand_tokens):
            return 55.0, {"mode": "remote", "note": f"Remote, but listed for {j.location}"}
        return 100.0, {"mode": "remote"}
    if not job_tokens:
        return 60.0, {"mode": j.work_mode, "note": "Job location not specified"}
    if not cand_tokens:
        return 50.0, {"mode": j.work_mode, "note": "Add your location to improve this score"}
    first = loc_tokens((j.location or "").split(",")[0])
    if first and first & cand_tokens:
        return 100.0, {"mode": j.work_mode, "note": "Same city"}
    if job_tokens & cand_tokens:
        return 70.0, {"mode": j.work_mode, "note": "Same country or region"}
    if c.relocation:
        return 45.0, {"mode": j.work_mode, "note": "Different location, open to relocation"}
    return 20.0, {"mode": j.work_mode, "note": "Different location"}


def score_preferences(c: CandidateSnapshot, j: JobSnapshot):
    parts, notes = [], {}
    if c.desired_titles:
        overlap = title_overlap(j.title, c.desired_titles)
        if overlap is not None:
            parts.append(100 * overlap)
    if c.work_modes and j.work_mode:
        ok = j.work_mode in c.work_modes
        parts.append(100.0 if ok else 0.0)
        notes["work_mode"] = ok
    if c.employment_types and j.employment_type:
        ok = j.employment_type in c.employment_types
        parts.append(100.0 if ok else 0.0)
        notes["employment_type"] = ok
    if c.min_salary and (j.salary_max or j.salary_min) and (not c.salary_currency or not j.salary_currency or c.salary_currency == j.salary_currency):
        offered = j.salary_max or j.salary_min
        parts.append(min(100.0, 100 * offered / c.min_salary))
        notes["salary_meets_minimum"] = offered >= c.min_salary
    if c.preferred_locations:
        wanted = set().union(*(loc_tokens(l) for l in c.preferred_locations))
        ok = j.work_mode == "remote" or bool(wanted & loc_tokens(j.location))
        parts.append(100.0 if ok else 0.0)
        notes["preferred_location"] = ok
    if not parts:
        return None, notes
    return sum(parts) / len(parts), notes


def score_semantic(c: CandidateSnapshot, j: JobSnapshot):
    if not c.text.strip():
        return None, {}
    value = embeddings.similarity(c.text, f"{j.title}\n{j.description}", j.embedding, j.embedding_model)
    return value, {"backend": embeddings.backend_name()}


def build_explanation(c: CandidateSnapshot, j: JobSnapshot, overall: float, parts: dict) -> dict:
    sk = parts["skills"]["detail"] if parts["skills"]["applicable"] else {}
    missing = sk.get("missing_required", [])
    suggestions = []
    if missing:
        suggestions.append(f"The job asks for {', '.join(missing[:5])}. If you have real experience with them, add it to your profile and CV with concrete examples; otherwise they are good skills to learn next.")
    if sk.get("missing_preferred"):
        suggestions.append(f"Nice-to-have skills you could add: {', '.join(sk['missing_preferred'][:5])}.")
    exp = parts["experience"]["detail"]
    if exp.get("required_years") and c.years < exp["required_years"]:
        suggestions.append(f"The role expects about {exp['required_years']:g} years of experience and your profile shows {c.years:g}. Highlight relevant projects, internships or freelance work.")
    if parts["education"]["applicable"] and parts["education"]["score"] < 100:
        suggestions.append("The role lists a higher education level than your profile shows. Add any degrees, courses or certifications that are relevant.")
    if parts["location"]["score"] is not None and parts["location"]["score"] < 60:
        suggestions.append("Location may be a barrier. Update your location and work arrangement preferences if you are flexible.")
    if not c.skills:
        suggestions.append("Upload a CV or add skills to your profile to get an accurate match.")
    if sk.get("missing_required") is not None and j.required:
        done = len(sk.get("matched_required", []))
        total = len(j.required)
        if not missing:
            summary = "Your profile covers all of the required technical skills for this job."
        elif done >= total / 2:
            summary = f"Your profile matches most of the required technical skills. Adding relevant {', '.join(missing[:3])} experience could improve your compatibility with this vacancy."
        else:
            summary = f"Your profile matches some of the requirements, but important skills such as {', '.join(missing[:3])} are not on your profile yet."
    else:
        summary = "The job does not list identifiable technical skills, so this score relies on experience, location and overall text similarity."
    return {
        "overall": overall,
        "summary": summary,
        "matched_skills": sk.get("matched_required", []) + sk.get("related_required", []),
        "exact_matched_skills": sk.get("matched_required", []),
        "related_skills": sk.get("related_required", []) + sk.get("related_preferred", []),
        "missing_required_skills": missing,
        "matched_preferred_skills": sk.get("matched_preferred", []),
        "missing_preferred_skills": sk.get("missing_preferred", []),
        "candidate_skills_not_requested": sorted(set(c.skills.values()) - set(j.required) - set(j.preferred))[:15],
        "experience": parts["experience"]["detail"],
        "education": parts["education"]["detail"],
        "location": parts["location"]["detail"],
        "preferences": parts["preferences"]["detail"],
        "suggestions": suggestions,
        "disclaimer": DISCLAIMER,
    }


def compute_match(c: CandidateSnapshot, j: JobSnapshot, weights: dict[str, float] | None = None) -> dict:
    weights = weights or DEFAULT_WEIGHTS
    scorers = {"skills": score_skills, "experience": score_experience, "education": score_education, "location": score_location, "semantic": score_semantic, "preferences": score_preferences}
    parts = {}
    for name, fn in scorers.items():
        score, detail = fn(c, j)
        if score is not None:
            score = max(0.0, min(100.0, float(score)))
        parts[name] = {"score": None if score is None else round(score, 1), "weight": weights[name], "applicable": score is not None, "detail": detail}
    active = {n: p for n, p in parts.items() if p["applicable"]}
    total_weight = sum(p["weight"] for p in active.values())
    overall = sum(p["score"] * p["weight"] for p in active.values()) / total_weight if total_weight else 0.0
    for p in parts.values():
        p["effective_weight"] = round(p["weight"] / total_weight, 3) if p["applicable"] and total_weight else 0.0
    overall = round(max(0.0, min(100.0, overall)), 1)
    return {"overall": overall, "components": parts, "explanation": build_explanation(c, j, overall, parts)}


def active_model(db: Session) -> MatchingModelVersion:
    model = db.scalar(select(MatchingModelVersion).where(MatchingModelVersion.is_active.is_(True)).order_by(MatchingModelVersion.id.desc()))
    if model is None:
        model = MatchingModelVersion(version="v1", weights=DEFAULT_WEIGHTS, is_active=True)
        db.add(model)
        db.flush()
    return model


def get_or_compute(db: Session, profile: CandidateProfile, job: Job, snapshot: CandidateSnapshot | None = None, model: MatchingModelVersion | None = None, signature: str | None = None, force: bool = False) -> dict:
    snapshot = snapshot or build_candidate_snapshot(db, profile)
    model = model or active_model(db)
    signature = signature or snapshot.signature()
    job_stamp = (aware(job.updated_at) or datetime.now(timezone.utc)).isoformat()
    full_sig = hashlib.sha256(f"{signature}|{job_stamp}|{model.id}|{embeddings.backend_name()}".encode()).hexdigest()
    existing = db.scalar(select(MatchScore).where(MatchScore.candidate_id == profile.id, MatchScore.job_id == job.id, MatchScore.model_version_id == model.id))
    if existing and existing.profile_hash == full_sig and existing.explanation and not force:
        return existing.explanation.explanation | {"score": existing.overall_score, "components": existing.explanation.explanation.get("components", {})}
    result = compute_match(snapshot, build_job_snapshot(job), model.weights)
    payload = result["explanation"] | {"components": result["components"], "model_version": model.version}
    row = existing or MatchScore(candidate_id=profile.id, job_id=job.id, model_version_id=model.id)
    row.overall_score = result["overall"]
    for name in ("skills", "experience", "education", "location", "semantic", "preferences"):
        setattr(row, f"{name}_score", result["components"][name]["score"])
    row.profile_hash = full_sig
    row.computed_at = datetime.now(timezone.utc)
    if existing is None:
        db.add(row)
        db.flush()
        db.add(MatchingExplanation(match_score_id=row.id, explanation=payload))
    else:
        if row.explanation is None:
            db.add(MatchingExplanation(match_score_id=row.id, explanation=payload))
        else:
            row.explanation.explanation = payload
    db.flush()
    return payload | {"score": result["overall"]}
