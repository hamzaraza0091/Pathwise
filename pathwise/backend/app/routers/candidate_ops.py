import math
import os
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.core.deps import require_roles
from app.models import (
    Application, ApplicationMessage, CandidateCertification, CandidateEducation, CandidateExperience, CandidateProfile, CandidateProject,
    CandidateSkill, Job, Resume, SavedJob, SearchHistory, User,
)
from app.routers.profiles import completion
from app.schemas.jobs import ApplyIn, EducationIn, ExperienceIn, MessageIn, NamedIn, SkillIn
from app.services import applications as app_service, matching, recommendations, resume as resume_service
from app.services.analytics import candidate_stats
from app.services.jobs import get_job_or_404
from app.services.serializers import application_dict, iso, job_dict
from app.services.skills import canonical

router = APIRouter(prefix="/api", tags=["candidate"])
candidate_only = require_roles("candidate")


def process_in_background(resume_id: int):
    with SessionLocal() as db:
        resume_service.process_resume(db, resume_id)


def resume_dict(resume: Resume, detail: bool = False) -> dict:
    data = {"id": resume.id, "filename": resume.original_filename, "size_bytes": resume.size_bytes, "status": resume.status, "error": resume.error, "is_active": resume.is_active, "uploaded_at": iso(resume.uploaded_at), "processed_at": iso(resume.processed_at)}
    if resume.extraction:
        data["confirmed"] = resume.extraction.confirmed_by_candidate
        data["method"] = resume.extraction.method
        if detail:
            data["extracted"] = resume.extraction.structured
            data["evidence"] = resume.extraction.evidence
            data["text_preview"] = (resume.extraction.raw_text or "")[:3000]
    return data


def own_resume(db: Session, user: User, resume_id: int) -> Resume:
    resume = db.scalar(select(Resume).options(selectinload(Resume.extraction)).where(Resume.id == resume_id, Resume.candidate_id == user.candidate_profile.id))
    if resume is None:
        raise HTTPException(404, "Resume not found")
    return resume


@router.post("/candidate/resumes", status_code=202)
async def upload_resume(background: BackgroundTasks, file: UploadFile = File(...), user: User = Depends(candidate_only), db: Session = Depends(get_db)):
    content = await file.read(settings.max_resume_bytes + 1)
    resume = resume_service.save_resume(db, user.candidate_profile, file, content)
    background.add_task(process_in_background, resume.id)
    return resume_dict(resume)


@router.get("/candidate/resumes")
def list_resumes(user: User = Depends(candidate_only), db: Session = Depends(get_db)):
    rows = db.scalars(select(Resume).options(selectinload(Resume.extraction)).where(Resume.candidate_id == user.candidate_profile.id).order_by(Resume.id.desc())).all()
    return [resume_dict(r) for r in rows]


@router.get("/candidate/resumes/{resume_id}")
def get_resume(resume_id: int, user: User = Depends(candidate_only), db: Session = Depends(get_db)):
    return resume_dict(own_resume(db, user, resume_id), detail=True)


@router.post("/candidate/resumes/{resume_id}/confirm")
def confirm_resume(resume_id: int, user: User = Depends(candidate_only), db: Session = Depends(get_db)):
    resume = own_resume(db, user, resume_id)
    if resume.extraction is None:
        raise HTTPException(400, "This resume has not been processed yet")
    resume.extraction.confirmed_by_candidate = True
    db.commit()
    return resume_dict(resume)


@router.post("/candidate/resumes/{resume_id}/activate")
def activate_resume(resume_id: int, user: User = Depends(candidate_only), db: Session = Depends(get_db)):
    resume = own_resume(db, user, resume_id)
    if resume.status != "processed" or resume.extraction is None:
        raise HTTPException(400, "Only successfully processed resumes can be activated")
    for other in db.scalars(select(Resume).where(Resume.candidate_id == user.candidate_profile.id)):
        other.is_active = other.id == resume.id
    resume_service.apply_extraction(db, user.candidate_profile, resume.extraction.structured)
    db.commit()
    return resume_dict(resume)


@router.post("/candidate/resumes/{resume_id}/reprocess", status_code=202)
def reprocess_resume(resume_id: int, background: BackgroundTasks, user: User = Depends(candidate_only), db: Session = Depends(get_db)):
    resume = own_resume(db, user, resume_id)
    resume.status, resume.error = "uploaded", None
    db.commit()
    background.add_task(process_in_background, resume.id)
    return resume_dict(resume)


@router.delete("/candidate/resumes/{resume_id}", status_code=204)
def delete_resume(resume_id: int, user: User = Depends(candidate_only), db: Session = Depends(get_db)):
    resume = own_resume(db, user, resume_id)
    path = Path(resume.stored_path)
    db.delete(resume)
    db.commit()
    path.unlink(missing_ok=True)
    return Response(status_code=204)


@router.get("/candidate/resumes/{resume_id}/download")
def download_resume(resume_id: int, user: User = Depends(candidate_only), db: Session = Depends(get_db)):
    resume = own_resume(db, user, resume_id)
    return file_response(resume)


def file_response(resume: Resume) -> FileResponse:
    root = Path(settings.storage_dir).resolve()
    path = Path(resume.stored_path).resolve()
    if root not in path.parents or not path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(path, media_type=resume.mime_type, filename=resume.original_filename, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


def profile_data(db: Session, profile: CandidateProfile) -> dict:
    cid = profile.id
    return {
        "skills": [{"id": s.id, "skill": s.skill, "kind": s.kind, "source": s.source, "evidence": s.evidence} for s in db.scalars(select(CandidateSkill).where(CandidateSkill.candidate_id == cid).order_by(CandidateSkill.kind.desc(), CandidateSkill.skill))],
        "education": [{"id": e.id, "degree": e.degree, "level": e.level, "institution": e.institution, "field_of_study": e.field_of_study, "end_year": e.end_year} for e in db.scalars(select(CandidateEducation).where(CandidateEducation.candidate_id == cid))],
        "experience": [{"id": e.id, "title": e.title, "company": e.company, "description": e.description, "start_date": e.start_date, "end_date": e.end_date, "months": e.months} for e in db.scalars(select(CandidateExperience).where(CandidateExperience.candidate_id == cid).order_by(CandidateExperience.start_date.desc()))],
        "certifications": [{"id": c.id, "name": c.name, "source": c.source, "evidence": c.evidence} for c in db.scalars(select(CandidateCertification).where(CandidateCertification.candidate_id == cid))],
        "projects": [{"id": p.id, "name": p.name, "description": p.description, "source": p.source, "evidence": p.evidence} for p in db.scalars(select(CandidateProject).where(CandidateProject.candidate_id == cid))],
    }


@router.get("/candidate/profile-data")
def get_profile_data(user: User = Depends(candidate_only), db: Session = Depends(get_db)):
    return profile_data(db, user.candidate_profile)


def touch(profile: CandidateProfile):
    from datetime import datetime, timezone

    profile.updated_at = datetime.now(timezone.utc)


@router.post("/candidate/skills", status_code=201)
def add_skill(data: SkillIn, user: User = Depends(candidate_only), db: Session = Depends(get_db)):
    profile = user.candidate_profile
    name = data.skill.strip()
    existing = db.scalar(select(CandidateSkill).where(CandidateSkill.candidate_id == profile.id, func.lower(CandidateSkill.skill) == canonical(name)))
    if existing:
        raise HTTPException(409, "You already have this skill")
    from app.services.skills import get_index

    known = get_index(db).by_name.get(canonical(name))
    row = CandidateSkill(candidate_id=profile.id, skill=known[0] if known else name, kind=known[1] if known else data.kind, source="manual")
    db.add(row)
    touch(profile)
    db.commit()
    return {"id": row.id, "skill": row.skill, "kind": row.kind, "source": row.source}


@router.delete("/candidate/skills/{skill_id}", status_code=204)
def delete_skill(skill_id: int, user: User = Depends(candidate_only), db: Session = Depends(get_db)):
    row = db.scalar(select(CandidateSkill).where(CandidateSkill.id == skill_id, CandidateSkill.candidate_id == user.candidate_profile.id))
    if row is None:
        raise HTTPException(404, "Skill not found")
    db.delete(row)
    touch(user.candidate_profile)
    db.commit()
    return Response(status_code=204)


def crud(path: str, model, schema, fields: list[str]):
    @router.post(f"/candidate/{path}", status_code=201, name=f"add_{path}")
    def create(data: schema, user: User = Depends(candidate_only), db: Session = Depends(get_db)):
        row = model(candidate_id=user.candidate_profile.id, **data.model_dump())
        if hasattr(row, "months") and row.months is None and getattr(row, "start_date", None):
            row.months = months_for(row.start_date, row.end_date)
        if hasattr(row, "source"):
            row.source = "manual"
        db.add(row)
        touch(user.candidate_profile)
        db.commit()
        return {"id": row.id}

    @router.put(f"/candidate/{path}/{{item_id}}", name=f"update_{path}")
    def update(item_id: int, data: schema, user: User = Depends(candidate_only), db: Session = Depends(get_db)):
        row = db.scalar(select(model).where(model.id == item_id, model.candidate_id == user.candidate_profile.id))
        if row is None:
            raise HTTPException(404, "Item not found")
        for key, value in data.model_dump().items():
            setattr(row, key, value)
        if hasattr(row, "months") and data.model_dump().get("months") is None and getattr(row, "start_date", None):
            row.months = months_for(row.start_date, row.end_date)
        if hasattr(row, "source"):
            row.source = "manual"
        touch(user.candidate_profile)
        db.commit()
        return {"id": row.id}

    @router.delete(f"/candidate/{path}/{{item_id}}", status_code=204, name=f"delete_{path}")
    def remove(item_id: int, user: User = Depends(candidate_only), db: Session = Depends(get_db)):
        row = db.scalar(select(model).where(model.id == item_id, model.candidate_id == user.candidate_profile.id))
        if row is None:
            raise HTTPException(404, "Item not found")
        db.delete(row)
        touch(user.candidate_profile)
        db.commit()
        return Response(status_code=204)


def months_for(start: str | None, end: str | None) -> int | None:
    from datetime import datetime, timezone

    if not start:
        return None
    sy, sm = map(int, start.split("-"))
    if end in (None, "present"):
        now = datetime.now(timezone.utc)
        ey, em = now.year, now.month
    else:
        ey, em = map(int, end.split("-"))
    return max(0, (ey - sy) * 12 + (em - sm) + 1)


crud("education", CandidateEducation, EducationIn, [])
crud("experience", CandidateExperience, ExperienceIn, [])
crud("certifications", CandidateCertification, NamedIn, [])
crud("projects", CandidateProject, NamedIn, [])


@router.get("/candidate/matches/{job_id}")
def match_detail(job_id: int, user: User = Depends(candidate_only), db: Session = Depends(get_db)):
    job = get_job_or_404(db, job_id)
    profile = user.candidate_profile
    snapshot = matching.build_candidate_snapshot(db, profile)
    if not snapshot.has_profile_data:
        raise HTTPException(400, "Upload a CV or add skills to your profile to see match details")
    result = matching.get_or_compute(db, profile, job, snapshot)
    db.commit()
    return {"job": job_dict(job, result["score"]), "match": result}


@router.get("/candidate/recommendations")
def get_recommendations(
    min_score: float | None = Query(None, ge=0, le=100), location: str | None = None, employment_type: str | None = None,
    experience_level: str | None = None, work_mode: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(12, ge=1, le=50),
    user: User = Depends(candidate_only), db: Session = Depends(get_db),
):
    profile = user.candidate_profile
    ranked = recommendations.rank(db, profile)
    saved = {r[0] for r in db.execute(select(SavedJob.job_id).where(SavedJob.candidate_id == profile.id))}
    filtered = recommendations.apply_filters(ranked, min_score, location, employment_type, experience_level, work_mode)
    window = filtered[(page - 1) * page_size: page * page_size]
    return {
        "items": [job_dict(r["job"], r["match"], None, r["job"].id in saved) | {"match_summary": r["explanation"]["summary"], "matched_skills": r["explanation"]["matched_skills"][:6], "missing_skills": r["explanation"]["missing_required_skills"][:4]} for r in window],
        "total": len(filtered), "page": page, "page_size": page_size, "pages": max(1, math.ceil(len(filtered) / page_size)),
        "needs_profile": not matching.build_candidate_snapshot(db, profile).has_profile_data,
        "high_match_threshold": settings.high_match_threshold,
    }


@router.get("/candidate/saved")
def saved_jobs(user: User = Depends(candidate_only), db: Session = Depends(get_db)):
    profile = user.candidate_profile
    snapshot = matching.build_candidate_snapshot(db, profile)
    rows = db.scalars(select(SavedJob).where(SavedJob.candidate_id == profile.id).order_by(SavedJob.id.desc())).all()
    out = []
    for row in rows:
        job = get_job_or_404(db, row.job_id)
        score = matching.get_or_compute(db, profile, job, snapshot)["score"] if snapshot.has_profile_data else None
        out.append(job_dict(job, score, None, True) | {"saved_at": iso(row.created_at)})
    db.commit()
    return out


@router.post("/jobs/{job_id}/apply", status_code=201)
def apply(job_id: int, data: ApplyIn, user: User = Depends(candidate_only), db: Session = Depends(get_db)):
    application = app_service.apply_to_job(db, user, job_id, data.cover_letter, data.resume_id)
    application = app_service.authorize_candidate(db, user, application.id)
    return application_dict(application)


@router.get("/candidate/applications")
def my_applications(status: str | None = None, user: User = Depends(candidate_only), db: Session = Depends(get_db)):
    query = select(Application).options(*app_service.eager()).where(Application.candidate_id == user.candidate_profile.id)
    if status:
        query = query.where(Application.status == status)
    return [application_dict(a) for a in db.scalars(query.order_by(Application.updated_at.desc()))]


@router.get("/candidate/applications/{application_id}")
def my_application(application_id: int, user: User = Depends(candidate_only), db: Session = Depends(get_db)):
    application = app_service.authorize_candidate(db, user, application_id)
    messages = db.scalars(select(ApplicationMessage).where(ApplicationMessage.application_id == application.id).order_by(ApplicationMessage.id)).all()
    return application_dict(application) | {"messages": [{"id": m.id, "mine": m.sender_id == user.id, "body": m.body, "at": iso(m.created_at)} for m in messages]}


@router.post("/candidate/applications/{application_id}/withdraw")
def withdraw_application(application_id: int, user: User = Depends(candidate_only), db: Session = Depends(get_db)):
    application = app_service.authorize_candidate(db, user, application_id)
    return application_dict(app_service.withdraw(db, user, application))


@router.post("/candidate/applications/{application_id}/messages", status_code=201)
def send_candidate_message(application_id: int, data: MessageIn, user: User = Depends(candidate_only), db: Session = Depends(get_db)):
    application = app_service.authorize_candidate(db, user, application_id)
    message = app_service.add_message(db, user, application, data.body)
    return {"id": message.id}


@router.get("/candidate/search-history")
def search_history(user: User = Depends(candidate_only), db: Session = Depends(get_db)):
    rows = db.scalars(select(SearchHistory).where(SearchHistory.user_id == user.id).order_by(SearchHistory.id.desc()).limit(20)).all()
    return [{"id": r.id, "query": r.query, "filters": r.filters, "result_count": r.result_count, "at": iso(r.created_at)} for r in rows]


@router.delete("/candidate/search-history", status_code=204)
def clear_search_history(user: User = Depends(candidate_only), db: Session = Depends(get_db)):
    db.execute(delete(SearchHistory).where(SearchHistory.user_id == user.id))
    db.commit()
    return Response(status_code=204)


@router.get("/candidate/dashboard")
def dashboard(user: User = Depends(candidate_only), db: Session = Depends(get_db)):
    profile = user.candidate_profile
    ranked = recommendations.rank(db, profile)
    high = [r for r in ranked if r["match"] >= settings.high_match_threshold]
    saved_ids = {r[0] for r in db.execute(select(SavedJob.job_id).where(SavedJob.candidate_id == profile.id))}
    missing_counter: dict[str, int] = {}
    for r in ranked[:30]:
        for skill in r["explanation"]["missing_required_skills"]:
            missing_counter[skill] = missing_counter.get(skill, 0) + 1
    resume = db.scalar(select(Resume).options(selectinload(Resume.extraction)).where(Resume.candidate_id == profile.id, Resume.is_active.is_(True)))
    applications = db.scalars(select(Application).options(*app_service.eager()).where(Application.candidate_id == profile.id).order_by(Application.updated_at.desc()).limit(5)).all()
    history = db.scalars(select(SearchHistory).where(SearchHistory.user_id == user.id).order_by(SearchHistory.id.desc()).limit(5)).all()
    data = profile_data(db, profile)
    return {
        "completion": completion(db, profile),
        "stats": candidate_stats(db, profile, len(ranked), len(high)),
        "resume": resume_dict(resume) if resume else None,
        "skills": [s for s in data["skills"] if s["kind"] == "technical"],
        "recommended": [job_dict(r["job"], r["match"], None, r["job"].id in saved_ids) for r in ranked[:6]],
        "applications": [application_dict(a) for a in applications],
        "search_history": [{"id": h.id, "query": h.query, "filters": h.filters, "result_count": h.result_count, "at": iso(h.created_at)} for h in history],
        "skill_suggestions": [{"skill": s, "jobs": n} for s, n in sorted(missing_counter.items(), key=lambda kv: -kv[1])[:6]],
        "email_preferences": user.email_preferences,
        "needs_profile": not matching.build_candidate_snapshot(db, profile).has_profile_data,
    }
