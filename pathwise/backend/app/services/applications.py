from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.constants import CANDIDATE_WITHDRAWABLE, EMPLOYER_TRANSITIONS
from app.core.config import settings
from app.models import Application, ApplicationMessage, ApplicationStatusHistory, CandidateProfile, Interview, Job, Resume, User
from app.models.users import utcnow
from app.services import matching
from app.services.jobs import company_scope
from app.services.notifications import audit, notify

LABELS = {
    "submitted": "Submitted", "viewed": "Viewed", "under_review": "Under review", "shortlisted": "Shortlisted",
    "interview_scheduled": "Interview scheduled", "offer": "Offer", "rejected": "Not selected", "withdrawn": "Withdrawn",
}


def eager():
    return (
        selectinload(Application.job).selectinload(Job.skills),
        selectinload(Application.job).selectinload(Job.source),
        selectinload(Application.candidate_profile_rel).selectinload(CandidateProfile.user),
        selectinload(Application.history),
        selectinload(Application.interviews),
        selectinload(Application.resume),
    )


def record(db: Session, application: Application, to_status: str, by: int | None, note: str | None = None):
    db.add(ApplicationStatusHistory(application_id=application.id, from_status=application.status, to_status=to_status, changed_by=by, note=note))
    application.status = to_status
    application.updated_at = utcnow()


def apply_to_job(db: Session, user: User, job_id: int, cover_letter: str | None, resume_id: int | None) -> Application:
    profile = user.candidate_profile
    job = db.scalar(select(Job).options(selectinload(Job.skills), selectinload(Job.source)).where(Job.id == job_id))
    if job is None or job.status != "active":
        raise HTTPException(404, "This job is not accepting applications")
    if not job.is_native_job:
        raise HTTPException(400, "This job was posted on another website. Use the 'Apply on Original Website' button to apply there")
    if settings.require_email_verification and not user.email_verified:
        raise HTTPException(403, "Please verify your email address before applying")
    if db.scalar(select(Application.id).where(Application.job_id == job_id, Application.candidate_id == profile.id)):
        raise HTTPException(409, "You have already applied to this job")
    resume = None
    if resume_id:
        resume = db.scalar(select(Resume).where(Resume.id == resume_id, Resume.candidate_id == profile.id))
        if resume is None:
            raise HTTPException(404, "Resume not found")
    else:
        resume = db.scalar(select(Resume).where(Resume.candidate_id == profile.id, Resume.is_active.is_(True)).order_by(Resume.id.desc()))
    score = None
    if profile is not None:
        score = matching.get_or_compute(db, profile, job)["score"]
    application = Application(job_id=job.id, candidate_id=profile.id, resume_id=resume.id if resume else None, cover_letter=(cover_letter or None), status="submitted", match_score=score)
    db.add(application)
    db.flush()
    db.add(ApplicationStatusHistory(application_id=application.id, from_status=None, to_status="submitted", changed_by=user.id))
    notify(db, user, "application_update", f"Application submitted: {job.title}", f"Your application to {job.title} at {job.company_name} was submitted.", "/candidate/applications")
    if job.posted_by:
        owner = db.get(User, job.posted_by)
        if owner:
            notify(db, owner, "employer_application", f"New application for {job.title}", f"{user.full_name} applied to {job.title}.", f"/employer/jobs/{job.id}/applications")
    audit(db, user.id, "application.submit", "application", application.id, {"job_id": job.id})
    db.commit()
    return application


def authorize_employer(db: Session, user: User, application_id: int) -> Application:
    application = db.scalar(select(Application).options(*eager()).where(Application.id == application_id))
    if application is None:
        raise HTTPException(404, "Application not found")
    company = company_scope(user)
    if user.role != "admin" and (company is None or application.job.company_id != company.id):
        raise HTTPException(404, "Application not found")
    return application


def authorize_candidate(db: Session, user: User, application_id: int) -> Application:
    application = db.scalar(select(Application).options(*eager()).where(Application.id == application_id))
    if application is None or application.candidate_id != user.candidate_profile.id:
        raise HTTPException(404, "Application not found")
    return application


def change_status(db: Session, actor: User, application: Application, to_status: str, note: str | None = None) -> Application:
    if to_status not in EMPLOYER_TRANSITIONS.get(application.status, set()):
        raise HTTPException(400, f"An application cannot move from '{LABELS[application.status]}' to '{LABELS.get(to_status, to_status)}'")
    record(db, application, to_status, actor.id, note)
    candidate = application.candidate_profile_rel.user
    notify(db, candidate, "application_update", f"{application.job.title}: {LABELS[to_status]}", f"Your application to {application.job.title} at {application.job.company_name} is now '{LABELS[to_status]}'." + (f"\n\nNote from the employer: {note}" if note else ""), "/candidate/applications")
    audit(db, actor.id, "application.status", "application", application.id, {"to": to_status})
    db.commit()
    return application


def withdraw(db: Session, user: User, application: Application) -> Application:
    if application.status not in CANDIDATE_WITHDRAWABLE:
        raise HTTPException(400, "This application can no longer be withdrawn")
    record(db, application, "withdrawn", user.id)
    audit(db, user.id, "application.withdraw", "application", application.id)
    db.commit()
    return application


def schedule_interview(db: Session, actor: User, application: Application, data: dict) -> Interview:
    if application.status in ("rejected", "withdrawn", "offer"):
        raise HTTPException(400, "Interviews cannot be scheduled for this application")
    when = data["scheduled_at"]
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    if when < datetime.now(timezone.utc):
        raise HTTPException(400, "Interview time must be in the future")
    interview = Interview(application_id=application.id, scheduled_at=when, duration_minutes=data.get("duration_minutes", 30), mode=data.get("mode", "video"), location_or_link=data.get("location_or_link"), notes=data.get("notes"), created_by=actor.id)
    db.add(interview)
    if application.status != "interview_scheduled":
        if "interview_scheduled" not in EMPLOYER_TRANSITIONS.get(application.status, set()):
            record(db, application, "under_review", actor.id)
        record(db, application, "interview_scheduled", actor.id, "Interview scheduled")
    candidate = application.candidate_profile_rel.user
    notify(
        db, candidate, "interview", f"Interview invitation: {application.job.title}",
        f"{application.job.company_name} invited you to an interview for {application.job.title} on {when:%A %d %B %Y at %H:%M} UTC ({interview.duration_minutes} min, {interview.mode})." + (f"\nWhere: {interview.location_or_link}" if interview.location_or_link else ""),
        "/candidate/applications",
    )
    audit(db, actor.id, "interview.schedule", "application", application.id)
    db.commit()
    return interview


def add_message(db: Session, sender: User, application: Application, body: str) -> ApplicationMessage:
    message = ApplicationMessage(application_id=application.id, sender_id=sender.id, body=body.strip())
    db.add(message)
    candidate_user = application.candidate_profile_rel.user
    if sender.id == candidate_user.id:
        owner = db.get(User, application.job.posted_by) if application.job.posted_by else None
        if owner:
            notify(db, owner, "message", f"Message from {sender.full_name}", body[:200], f"/employer/jobs/{application.job_id}/applications")
    else:
        notify(db, candidate_user, "message", f"Message about {application.job.title}", body[:200], "/candidate/applications")
    db.commit()
    return message
