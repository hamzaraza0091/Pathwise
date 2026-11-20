from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Application, CandidateProfile, Company, IngestionLog, Job, JobSource, JobView, MatchScore, Notification, Report, SavedJob,
    SearchHistory, SourceSyncRun, User,
)
from app.models.users import utcnow


def candidate_stats(db: Session, profile: CandidateProfile, recommended_total: int, high_match: int) -> dict:
    statuses = dict(db.execute(select(Application.status, func.count()).where(Application.candidate_id == profile.id).group_by(Application.status)).all())
    return {
        "recommended_total": recommended_total, "high_match_jobs": high_match,
        "applied": sum(statuses.values()), "saved": db.scalar(select(func.count()).select_from(SavedJob).where(SavedJob.candidate_id == profile.id)) or 0,
        "under_review": statuses.get("under_review", 0) + statuses.get("viewed", 0) + statuses.get("submitted", 0), "by_status": statuses,
    }


def employer_stats(db: Session, company_id: int) -> dict:
    job_ids = [r[0] for r in db.execute(select(Job.id).where(Job.company_id == company_id, Job.posted_by.is_not(None)))]
    by_status_jobs = dict(db.execute(select(Job.status, func.count()).where(Job.company_id == company_id, Job.posted_by.is_not(None)).group_by(Job.status)).all())
    apps = dict(db.execute(select(Application.status, func.count()).where(Application.job_id.in_(job_ids)).group_by(Application.status)).all()) if job_ids else {}
    since = utcnow() - timedelta(days=29)
    daily = {}
    if job_ids:
        for (created,) in db.execute(select(Application.created_at).where(Application.job_id.in_(job_ids), Application.created_at >= since)):
            day = created.date().isoformat()
            daily[day] = daily.get(day, 0) + 1
    series = [{"date": (since + timedelta(days=i)).date().isoformat(), "applications": daily.get((since + timedelta(days=i)).date().isoformat(), 0)} for i in range(30)]
    per_job = []
    if job_ids:
        views = dict(db.execute(select(JobView.job_id, func.count()).where(JobView.job_id.in_(job_ids)).group_by(JobView.job_id)).all())
        counts = dict(db.execute(select(Application.job_id, func.count()).where(Application.job_id.in_(job_ids)).group_by(Application.job_id)).all())
        avg = dict(db.execute(select(Application.job_id, func.avg(Application.match_score)).where(Application.job_id.in_(job_ids)).group_by(Application.job_id)).all())
        for job in db.scalars(select(Job).where(Job.id.in_(job_ids)).order_by(Job.id.desc()).limit(10)):
            per_job.append({"job_id": job.id, "title": job.title, "views": views.get(job.id, 0), "applications": counts.get(job.id, 0), "avg_match": round(avg.get(job.id) or 0, 1)})
    hired = apps.get("offer", 0)
    total = sum(apps.values())
    return {
        "jobs_by_status": by_status_jobs, "active_jobs": by_status_jobs.get("active", 0), "total_applications": total, "applications_by_status": apps,
        "shortlisted": apps.get("shortlisted", 0), "interviews": apps.get("interview_scheduled", 0), "offers": hired,
        "offer_rate": round(100 * hired / total, 1) if total else 0, "daily_applications": series, "per_job": per_job,
    }


def admin_stats(db: Session) -> dict:
    roles = dict(db.execute(select(User.role, func.count()).group_by(User.role)).all())
    jobs_by_source = [{"source": name, "jobs": count} for name, count in db.execute(select(JobSource.name, func.count(Job.id)).join(Job, Job.source_id == JobSource.id).where(Job.status == "active").group_by(JobSource.name))]
    runs = db.execute(select(SourceSyncRun.status, func.count()).group_by(SourceSyncRun.status)).all()
    since = utcnow() - timedelta(days=13)
    signups = {}
    for (created,) in db.execute(select(User.created_at).where(User.created_at >= since)):
        signups[created.date().isoformat()] = signups.get(created.date().isoformat(), 0) + 1
    return {
        "users_by_role": roles, "total_users": sum(roles.values()), "companies": db.scalar(select(func.count()).select_from(Company).where(Company.is_external.is_(False))) or 0,
        "jobs_by_status": dict(db.execute(select(Job.status, func.count()).group_by(Job.status)).all()), "jobs_by_source": jobs_by_source,
        "applications": db.scalar(select(func.count()).select_from(Application)) or 0, "open_reports": db.scalar(select(func.count()).select_from(Report).where(Report.status == "open")) or 0,
        "pending_review": db.scalar(select(func.count()).select_from(Job).where(Job.status == "pending_review")) or 0,
        "sync_runs_by_status": {s: c for s, c in runs}, "signups": [{"date": (since + timedelta(days=i)).date().isoformat(), "signups": signups.get((since + timedelta(days=i)).date().isoformat(), 0)} for i in range(14)],
        "match_scores_computed": db.scalar(select(func.count()).select_from(MatchScore)) or 0,
    }
