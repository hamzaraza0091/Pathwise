import re
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models import Company, Job, JobCategory, JobLocation, JobSkill, JobSource, User
from app.models.users import utcnow
from app.services import embeddings
from app.services.normalize import (
    aware, clean_title, dedupe_hash, extract_education_required, extract_min_years, infer_level, infer_work_mode,
    map_category, normalize_key, split_location,
)
from app.services.skills import canonical, classify_job_skills

SUSPICIOUS = re.compile(r"(wire transfer|western union|send (us )?(a )?(fee|deposit)|pay (a |an )?(registration|training|processing) fee|crypto(currency)? investment|guaranteed income|no experience.{0,30}\$\d{3,}.{0,15}(per|a) (day|hour)|whatsapp only|telegram only|gift cards?)", re.I)
FREE_MAIL = re.compile(r"@(gmail|yahoo|hotmail|outlook|proton|aol)\.", re.I)
SORT_FIELDS = {"date", "relevance", "salary", "match"}


def fts_ready(db: Session) -> bool:
    return db.execute(text("SELECT 1 FROM sqlite_master WHERE name='jobs_fts'")).first() is not None


def index_job(db: Session, job: Job):
    if not fts_ready(db):
        return
    db.execute(text("DELETE FROM jobs_fts WHERE rowid = :id"), {"id": job.id})
    if job.status == "active":
        skills = " ".join(s.skill for s in job.skills)
        db.execute(
            text("INSERT INTO jobs_fts(rowid, title, company_name, body, skills) VALUES (:id, :t, :c, :b, :s)"),
            {"id": job.id, "t": job.title, "c": job.company_name, "b": (job.description or "")[:30000], "s": skills},
        )


def reindex_all(db: Session) -> int:
    if not fts_ready(db):
        return 0
    db.execute(text("DELETE FROM jobs_fts"))
    count = 0
    for job in db.scalars(select(Job).options(selectinload(Job.skills)).where(Job.status == "active")):
        index_job(db, job)
        count += 1
    db.commit()
    return count


def get_category(db: Session, name: str) -> JobCategory:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    category = db.scalar(select(JobCategory).where(JobCategory.slug == slug))
    if category is None:
        category = JobCategory(name=name, slug=slug)
        db.add(category)
        db.flush()
    return category


def set_job_skills(job: Job, required: list[str], preferred: list[str]):
    job.skills.clear()
    seen = set()
    for skill in required:
        if canonical(skill) not in seen:
            seen.add(canonical(skill))
            job.skills.append(JobSkill(skill=skill.strip()[:120], is_required=True))
    for skill in preferred:
        if canonical(skill) not in seen:
            seen.add(canonical(skill))
            job.skills.append(JobSkill(skill=skill.strip()[:120], is_required=False))


def set_job_location(job: Job):
    job.locations.clear()
    city, country = split_location(job.location)
    if city or country or job.work_mode == "remote":
        job.locations.append(JobLocation(city=city, country=country, is_remote=job.work_mode == "remote"))


def embed_job(job: Job):
    if embeddings.has_dense():
        vectors = embeddings.embed_dense([f"{job.title}\n{job.description}"])
        if vectors is not None:
            job.embedding = embeddings.to_blob(vectors[0])
            job.embedding_model = settings.embedding_model


def is_suspicious(title: str, description: str, apply_url: str | None, salary_max: float | None) -> bool:
    blob = f"{title}\n{description}"
    if SUSPICIOUS.search(blob):
        return True
    if apply_url and FREE_MAIL.search(apply_url):
        return True
    return bool(salary_max and salary_max > 1_000_000)


def native_source(db: Session) -> JobSource:
    source = db.scalar(select(JobSource).where(JobSource.is_native.is_(True)))
    if source is None:
        source = JobSource(key="pathwise", name="Pathwise", is_native=True, refresh_minutes=0)
        db.add(source)
        db.flush()
    return source


def company_scope(user: User) -> Company | None:
    if user.role == "employer" and user.employer_profile:
        return user.employer_profile.company
    if user.role == "recruiter" and user.recruiter_profile and user.recruiter_profile.company_id:
        from sqlalchemy.orm import object_session

        return object_session(user).get(Company, user.recruiter_profile.company_id)
    return None


def require_company(user: User) -> Company:
    company = company_scope(user)
    if company is None:
        raise HTTPException(400, "Create your company profile before managing jobs")
    return company


def create_native_job(db: Session, user: User, data: dict) -> Job:
    company = require_company(user)
    if settings.require_email_verification and not user.email_verified:
        raise HTTPException(403, "Please verify your email address before publishing jobs")
    required = [s for s in data.pop("required_skills", [])]
    preferred = [s for s in data.pop("preferred_skills", [])]
    category_name = data.pop("category", None)
    description = data["description"].strip()
    title = clean_title(data["title"])
    work_mode = data.get("work_mode") or infer_work_mode(data.get("location"), title, description, None)
    if not required and not preferred:
        required, preferred = classify_job_skills(db, f"{title}\n{description}")
    suspicious = is_suspicious(title, description, data.get("application_url"), data.get("salary_max"))
    category = get_category(db, category_name or map_category(title))
    job = Job(
        title=title, company_id=company.id, company_name=company.name, description=description, category_id=category.id,
        employment_type=data.get("employment_type") or "full_time",
        experience_level=data.get("experience_level") or infer_level(title, description),
        work_mode=work_mode, location=data.get("location"), salary_min=data.get("salary_min"), salary_max=data.get("salary_max"),
        salary_currency=data.get("salary_currency"), salary_period=data.get("salary_period") or "year",
        min_years=data.get("min_years") if data.get("min_years") is not None else extract_min_years(description),
        education_required=data.get("education_required") or extract_education_required(description),
        source_id=native_source(db).id, posted_by=user.id, application_url=data.get("application_url"),
        status="pending_review" if suspicious else "active", published_at=utcnow(),
        expires_at=data.get("expires_at") or utcnow() + timedelta(days=settings.job_default_ttl_days), last_seen_at=utcnow(),
    )
    job.dedupe_hash = dedupe_hash(title, company.name, job.location, work_mode == "remote")
    db.add(job)
    db.flush()
    set_job_skills(job, required, preferred)
    set_job_location(job)
    embed_job(job)
    db.flush()
    index_job(db, job)
    if suspicious:
        from app.models import Report

        db.add(Report(job_id=job.id, reporter_id=None, reason="auto_flagged", details="Automatically flagged for suspicious wording or contact details"))
    return job


def update_native_job(db: Session, user: User, job: Job, data: dict) -> Job:
    required = data.pop("required_skills", None)
    preferred = data.pop("preferred_skills", None)
    category_name = data.pop("category", None)
    for key, value in data.items():
        if key == "title" and value:
            value = clean_title(value)
        setattr(job, key, value)
    if category_name:
        job.category_id = get_category(db, category_name).id
    if required is not None or preferred is not None:
        set_job_skills(job, required or [s.skill for s in job.skills if s.is_required] if required is None else required, preferred if preferred is not None else [s.skill for s in job.skills if not s.is_required])
    if "description" in data or "title" in data:
        if is_suspicious(job.title, job.description, job.application_url, job.salary_max) and job.status == "active":
            job.status = "pending_review"
        job.min_years = data.get("min_years", job.min_years)
        embed_job(job)
    job.dedupe_hash = dedupe_hash(job.title, job.company_name, job.location, job.work_mode == "remote")
    set_job_location(job)
    job.updated_at = utcnow()
    db.flush()
    index_job(db, job)
    return job


def set_job_status(db: Session, job: Job, status: str):
    job.status = status
    job.updated_at = utcnow()
    db.flush()
    index_job(db, job)


def get_job_or_404(db: Session, job_id: int) -> Job:
    job = db.scalar(select(Job).options(selectinload(Job.skills), selectinload(Job.source), selectinload(Job.category), selectinload(Job.company)).where(Job.id == job_id))
    if job is None:
        raise HTTPException(404, "Job not found")
    return job


def owned_job(db: Session, user: User, job_id: int) -> Job:
    job = get_job_or_404(db, job_id)
    company = company_scope(user)
    if user.role != "admin" and (company is None or job.company_id != company.id or not job.is_native_job):
        raise HTTPException(404, "Job not found")
    return job


def expire_stale_jobs(db: Session) -> int:
    now = utcnow()
    expired = 0
    for job in db.scalars(select(Job).options(selectinload(Job.skills)).where(Job.status == "active", Job.expires_at.is_not(None), Job.expires_at < now)):
        set_job_status(db, job, "expired")
        expired += 1
    db.commit()
    return expired


def job_stats(db: Session) -> dict:
    rows = db.execute(select(Job.status, func.count()).group_by(Job.status)).all()
    return {status: count for status, count in rows}
