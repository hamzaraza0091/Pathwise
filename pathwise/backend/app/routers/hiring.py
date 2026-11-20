import math

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.deps import require_roles
from app.models import (
    Application, ApplicationMessage, CandidateProfile, CandidateSkill, Company, EmployerShortlist, Job, RecruiterProfile, Resume, User,
)
from app.routers.candidate_ops import file_response, profile_data
from app.schemas.jobs import InterviewIn, JobIn, JobUpdate, MessageIn, RecruiterAttachIn, ShortlistIn, StatusIn
from app.services import analytics, applications as app_service, jobs as job_service, matching
from app.services.jobs import company_scope, require_company
from app.services.notifications import audit
from app.services.serializers import application_dict, iso, job_dict

router = APIRouter(prefix="/api/hiring", tags=["hiring (employer and recruiter)"])
hiring_user = require_roles("employer", "recruiter", "admin")
manager_only = require_roles("employer")


def scoped(user: User) -> Company:
    return require_company(user)


def job_summary(db: Session, job: Job) -> dict:
    counts = dict(db.execute(select(Application.status, func.count()).where(Application.job_id == job.id).group_by(Application.status)).all())
    return job_dict(job) | {"application_count": sum(counts.values()), "applications_by_status": counts}


@router.get("/jobs")
def my_jobs(status: str | None = None, user: User = Depends(hiring_user), db: Session = Depends(get_db)):
    company = scoped(user)
    query = select(Job).options(selectinload(Job.skills), selectinload(Job.source), selectinload(Job.category), selectinload(Job.company)).where(Job.company_id == company.id, Job.posted_by.is_not(None))
    if status:
        query = query.where(Job.status == status)
    return [job_summary(db, j) for j in db.scalars(query.order_by(Job.id.desc()))]


@router.post("/jobs", status_code=201)
def create_job(data: JobIn, user: User = Depends(hiring_user), db: Session = Depends(get_db)):
    job = job_service.create_native_job(db, user, data.model_dump())
    audit(db, user.id, "job.create", "job", job.id)
    db.commit()
    job = job_service.get_job_or_404(db, job.id)
    return job_dict(job, detail=True)


@router.get("/jobs/{job_id}")
def get_my_job(job_id: int, user: User = Depends(hiring_user), db: Session = Depends(get_db)):
    return job_dict(job_service.owned_job(db, user, job_id), detail=True)


@router.put("/jobs/{job_id}")
def update_job(job_id: int, data: JobUpdate, user: User = Depends(hiring_user), db: Session = Depends(get_db)):
    job = job_service.owned_job(db, user, job_id)
    if job.status in ("removed",):
        raise HTTPException(400, "This job was removed by a moderator")
    job_service.update_native_job(db, user, job, data.model_dump(exclude_unset=True))
    audit(db, user.id, "job.update", "job", job.id)
    db.commit()
    return job_dict(job_service.get_job_or_404(db, job.id), detail=True)


@router.post("/jobs/{job_id}/close")
def close_job(job_id: int, user: User = Depends(hiring_user), db: Session = Depends(get_db)):
    job = job_service.owned_job(db, user, job_id)
    job_service.set_job_status(db, job, "closed")
    audit(db, user.id, "job.close", "job", job.id)
    db.commit()
    return {"status": "closed"}


@router.post("/jobs/{job_id}/reopen")
def reopen_job(job_id: int, user: User = Depends(hiring_user), db: Session = Depends(get_db)):
    job = job_service.owned_job(db, user, job_id)
    if job.status in ("removed", "pending_review"):
        raise HTTPException(400, "This job needs moderator approval before it can be reopened")
    from datetime import timedelta

    from app.core.config import settings
    from app.models.users import utcnow

    job.expires_at = utcnow() + timedelta(days=settings.job_default_ttl_days)
    job_service.set_job_status(db, job, "active")
    db.commit()
    return {"status": "active"}


@router.get("/applications")
def all_applications(job_id: int | None = None, status: str | None = None, sort: str = Query("match", pattern="^(match|date)$"), user: User = Depends(hiring_user), db: Session = Depends(get_db)):
    company = scoped(user)
    query = select(Application).options(*app_service.eager()).join(Job, Job.id == Application.job_id).where(Job.company_id == company.id)
    if job_id:
        query = query.where(Application.job_id == job_id)
    if status:
        query = query.where(Application.status == status)
    query = query.order_by(Application.match_score.desc().nulls_last() if sort == "match" else Application.id.desc())
    return [application_dict(a, include_candidate=True) for a in db.scalars(query)]


@router.get("/applications/{application_id}")
def application_detail(application_id: int, user: User = Depends(hiring_user), db: Session = Depends(get_db)):
    application = app_service.authorize_employer(db, user, application_id)
    profile = application.candidate_profile_rel
    snapshot = matching.build_candidate_snapshot(db, profile)
    match = matching.get_or_compute(db, profile, application.job, snapshot) if snapshot.has_profile_data else None
    messages = db.scalars(select(ApplicationMessage).where(ApplicationMessage.application_id == application.id).order_by(ApplicationMessage.id)).all()
    if application.status == "submitted":
        app_service.record(db, application, "viewed", user.id, None)
        app_service.notify(db, profile.user, "application_update", f"{application.job.title}: Viewed", f"{application.job.company_name} viewed your application for {application.job.title}.", "/candidate/applications")
    db.commit()
    return application_dict(application, include_candidate=True) | {
        "match": match, "profile": profile_data(db, profile),
        "messages": [{"id": m.id, "mine": m.sender_id == user.id, "body": m.body, "at": iso(m.created_at)} for m in messages],
    }


@router.post("/applications/{application_id}/status")
def set_status(application_id: int, data: StatusIn, user: User = Depends(hiring_user), db: Session = Depends(get_db)):
    application = app_service.authorize_employer(db, user, application_id)
    if data.status == "interview_scheduled":
        raise HTTPException(400, "Use the interview scheduling form to move an application to the interview stage")
    return application_dict(app_service.change_status(db, user, application, data.status, data.note), include_candidate=True)


@router.post("/applications/{application_id}/interviews", status_code=201)
def create_interview(application_id: int, data: InterviewIn, user: User = Depends(hiring_user), db: Session = Depends(get_db)):
    application = app_service.authorize_employer(db, user, application_id)
    interview = app_service.schedule_interview(db, user, application, data.model_dump())
    return {"id": interview.id, "scheduled_at": iso(interview.scheduled_at)}


@router.post("/applications/{application_id}/messages", status_code=201)
def send_message(application_id: int, data: MessageIn, user: User = Depends(hiring_user), db: Session = Depends(get_db)):
    application = app_service.authorize_employer(db, user, application_id)
    return {"id": app_service.add_message(db, user, application, data.body).id}


@router.get("/applications/{application_id}/resume")
def application_resume(application_id: int, user: User = Depends(hiring_user), db: Session = Depends(get_db)):
    application = app_service.authorize_employer(db, user, application_id)
    if application.resume is None:
        raise HTTPException(404, "This applicant did not attach a resume")
    audit(db, user.id, "resume.download", "application", application.id)
    db.commit()
    return file_response(application.resume)


@router.get("/interviews")
def interviews(user: User = Depends(hiring_user), db: Session = Depends(get_db)):
    company = scoped(user)
    apps = db.scalars(select(Application).options(*app_service.eager()).join(Job, Job.id == Application.job_id).where(Job.company_id == company.id, Application.status == "interview_scheduled")).all()
    rows = []
    for a in apps:
        for i in a.interviews:
            rows.append({"id": i.id, "application_id": a.id, "candidate": a.candidate_profile_rel.user.full_name, "job_title": a.job.title, "scheduled_at": iso(i.scheduled_at), "duration_minutes": i.duration_minutes, "mode": i.mode, "location_or_link": i.location_or_link, "status": i.status})
    return sorted(rows, key=lambda r: r["scheduled_at"])


def has_applied(db: Session, company: Company, profile: CandidateProfile) -> bool:
    return bool(db.scalar(select(Application.id).join(Job, Job.id == Application.job_id).where(Job.company_id == company.id, Application.candidate_id == profile.id, Application.status != "withdrawn").limit(1)))


@router.get("/candidates")
def discover(
    q: str | None = None, skills: str | None = None, location: str | None = None, min_years: float | None = Query(None, ge=0), job_id: int | None = None,
    min_match: int | None = Query(None, ge=0, le=100), page: int = Query(1, ge=1), page_size: int = Query(12, ge=1, le=40),
    user: User = Depends(hiring_user), db: Session = Depends(get_db),
):
    company = scoped(user)
    job = job_service.owned_job(db, user, job_id) if job_id else None
    query = select(CandidateProfile).options(selectinload(CandidateProfile.user)).join(User, User.id == CandidateProfile.user_id).where(CandidateProfile.discoverable.is_(True), User.is_active.is_(True))
    if location:
        query = query.where(CandidateProfile.location.ilike(f"%{location}%"))
    if min_years is not None:
        query = query.where(CandidateProfile.years_experience >= min_years)
    for skill in [s.strip().lower() for s in (skills or "").split(",") if s.strip()]:
        query = query.where(select(CandidateSkill.id).where(CandidateSkill.candidate_id == CandidateProfile.id, func.lower(CandidateSkill.skill) == skill).exists())
    if q:
        like = f"%{q}%"
        query = query.where(or_(CandidateProfile.headline.ilike(like), CandidateProfile.summary.ilike(like), select(CandidateSkill.id).where(CandidateSkill.candidate_id == CandidateProfile.id, CandidateSkill.skill.ilike(like)).exists()))
    profiles = db.scalars(query.order_by(CandidateProfile.updated_at.desc()).limit(300)).all()
    shortlisted = {(r.candidate_id, r.job_id) for r in db.scalars(select(EmployerShortlist).where(EmployerShortlist.owner_user_id == user.id))}
    items = []
    for profile in profiles:
        skill_rows = [s.skill for s in db.scalars(select(CandidateSkill).where(CandidateSkill.candidate_id == profile.id, CandidateSkill.kind == "technical"))]
        score = None
        if job is not None:
            score = matching.get_or_compute(db, profile, job)["score"]
            if min_match is not None and score < min_match:
                continue
        items.append({"id": profile.id, "name": profile.user.full_name, "headline": profile.headline, "location": profile.location, "years_experience": profile.years_experience, "experience_level": profile.experience_level, "skills": skill_rows[:12], "match": None if score is None else round(score), "shortlisted": (profile.id, job_id) in shortlisted or (profile.id, None) in shortlisted, "can_view_resume": profile.resume_visible_to_employers})
    db.commit()
    if job is not None:
        items.sort(key=lambda i: -(i["match"] or 0))
    total = len(items)
    return {"items": items[(page - 1) * page_size: page * page_size], "total": total, "page": page, "page_size": page_size, "pages": max(1, math.ceil(total / page_size))}


def authorize_profile(db: Session, user: User, candidate_id: int) -> tuple[CandidateProfile, bool]:
    company = scoped(user)
    profile = db.scalar(select(CandidateProfile).options(selectinload(CandidateProfile.user)).where(CandidateProfile.id == candidate_id))
    if profile is None:
        raise HTTPException(404, "Candidate not found")
    applied = has_applied(db, company, profile)
    if not applied and not profile.discoverable:
        raise HTTPException(404, "Candidate not found")
    return profile, applied


@router.get("/candidates/{candidate_id}")
def candidate_profile(candidate_id: int, job_id: int | None = None, user: User = Depends(hiring_user), db: Session = Depends(get_db)):
    profile, applied = authorize_profile(db, user, candidate_id)
    job = job_service.owned_job(db, user, job_id) if job_id else None
    match = matching.get_or_compute(db, profile, job) if job else None
    db.commit()
    resume = db.scalar(select(Resume).where(Resume.candidate_id == profile.id, Resume.is_active.is_(True)))
    return {
        "id": profile.id, "name": profile.user.full_name, "headline": profile.headline, "summary": profile.summary, "location": profile.location,
        "years_experience": profile.years_experience, "experience_level": profile.experience_level,
        "email": profile.user.email if applied else None, "phone": profile.phone if applied else None, "linkedin_url": profile.linkedin_url, "portfolio_url": profile.portfolio_url,
        "data": {k: v for k, v in profile_data(db, profile).items()}, "match": match, "has_applied": applied,
        "resume_available": bool(resume and (applied or profile.resume_visible_to_employers)),
    }


@router.get("/candidates/{candidate_id}/resume")
def candidate_resume(candidate_id: int, user: User = Depends(hiring_user), db: Session = Depends(get_db)):
    profile, applied = authorize_profile(db, user, candidate_id)
    if not (applied or profile.resume_visible_to_employers):
        raise HTTPException(403, "This candidate has not shared their CV with employers")
    resume = db.scalar(select(Resume).where(Resume.candidate_id == profile.id, Resume.is_active.is_(True)))
    if resume is None:
        raise HTTPException(404, "No resume available")
    audit(db, user.id, "resume.download", "candidate", profile.id)
    db.commit()
    return file_response(resume)


@router.get("/shortlist")
def get_shortlist(user: User = Depends(hiring_user), db: Session = Depends(get_db)):
    company = scoped(user)
    rows = db.scalars(select(EmployerShortlist).where(EmployerShortlist.owner_user_id == user.id).order_by(EmployerShortlist.id.desc())).all()
    out = []
    for row in rows:
        profile = db.scalar(select(CandidateProfile).options(selectinload(CandidateProfile.user)).where(CandidateProfile.id == row.candidate_id))
        if profile is None:
            continue
        out.append({"id": row.id, "candidate_id": profile.id, "name": profile.user.full_name, "headline": profile.headline, "location": profile.location, "job_id": row.job_id, "note": row.note, "created_at": iso(row.created_at)})
    return out


@router.post("/shortlist", status_code=201)
def add_shortlist(data: ShortlistIn, user: User = Depends(hiring_user), db: Session = Depends(get_db)):
    profile, _ = authorize_profile(db, user, data.candidate_id)
    if data.job_id:
        job_service.owned_job(db, user, data.job_id)
    exists = db.scalar(select(EmployerShortlist.id).where(EmployerShortlist.owner_user_id == user.id, EmployerShortlist.candidate_id == profile.id, EmployerShortlist.job_id.is_(data.job_id) if data.job_id is None else EmployerShortlist.job_id == data.job_id))
    if exists:
        raise HTTPException(409, "Candidate is already shortlisted")
    db.add(EmployerShortlist(owner_user_id=user.id, candidate_id=profile.id, job_id=data.job_id, note=data.note))
    db.commit()
    return {"shortlisted": True}


@router.delete("/shortlist/{item_id}", status_code=204)
def remove_shortlist(item_id: int, user: User = Depends(hiring_user), db: Session = Depends(get_db)):
    row = db.scalar(select(EmployerShortlist).where(EmployerShortlist.id == item_id, EmployerShortlist.owner_user_id == user.id))
    if row is None:
        raise HTTPException(404, "Not found")
    db.delete(row)
    db.commit()
    return Response(status_code=204)


@router.get("/analytics")
def hiring_analytics(user: User = Depends(hiring_user), db: Session = Depends(get_db)):
    return analytics.employer_stats(db, scoped(user).id)


@router.get("/recruiters")
def team(user: User = Depends(manager_only), db: Session = Depends(get_db)):
    company = scoped(user)
    rows = db.scalars(select(RecruiterProfile).options(selectinload(RecruiterProfile.user)).where(RecruiterProfile.company_id == company.id)).all()
    return [{"user_id": r.user_id, "name": r.user.full_name, "email": r.user.email, "specialization": r.specialization} for r in rows]


@router.post("/recruiters", status_code=201)
def attach_recruiter(data: RecruiterAttachIn, user: User = Depends(manager_only), db: Session = Depends(get_db)):
    company = scoped(user)
    target = db.scalar(select(User).where(User.email == data.email.lower(), User.role == "recruiter"))
    if target is None or target.recruiter_profile is None:
        raise HTTPException(404, "No recruiter account found with that email address")
    if target.recruiter_profile.company_id and target.recruiter_profile.company_id != company.id:
        raise HTTPException(409, "This recruiter is already assigned to another company")
    target.recruiter_profile.company_id = company.id
    audit(db, user.id, "recruiter.attach", "user", target.id)
    db.commit()
    return {"attached": True}


@router.delete("/recruiters/{user_id}", status_code=204)
def detach_recruiter(user_id: int, user: User = Depends(manager_only), db: Session = Depends(get_db)):
    company = scoped(user)
    profile = db.scalar(select(RecruiterProfile).where(RecruiterProfile.user_id == user_id, RecruiterProfile.company_id == company.id))
    if profile is None:
        raise HTTPException(404, "Recruiter not found")
    profile.company_id = None
    db.commit()
    return Response(status_code=204)
