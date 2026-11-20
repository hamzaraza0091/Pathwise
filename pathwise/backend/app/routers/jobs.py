import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.deps import get_current_user, get_optional_user
from app.models import Application, Company, Job, JobCategory, JobSource, JobView, Report, SavedJob, User
from app.schemas.jobs import JobPage, ReportIn
from app.services import jobs as job_service, matching, search as search_service
from app.services.jobs import company_scope
from app.services.notifications import audit
from app.services.serializers import job_dict

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
companies = APIRouter(prefix="/api/companies", tags=["companies"])


def csv(value: str | None) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()] if value else []


def candidate_context(db: Session, user: User | None):
    if user is None or user.role != "candidate" or user.candidate_profile is None:
        return None
    snapshot = matching.build_candidate_snapshot(db, user.candidate_profile)
    return (user.candidate_profile, snapshot, matching.active_model(db)) if snapshot.has_profile_data else None


@router.get("", response_model=JobPage)
def list_jobs(
    q: str | None = Query(None, max_length=200),
    title: str | None = None,
    company: str | None = None,
    location: str | None = None,
    skills: str | None = Query(None, description="Comma separated skills; all must be present"),
    work_mode: str | None = Query(None, description="Comma separated: remote,onsite,hybrid"),
    employment_type: str | None = None,
    experience_level: str | None = None,
    category: str | None = None,
    source: str | None = None,
    salary_min: float | None = Query(None, ge=0),
    salary_max: float | None = Query(None, ge=0),
    posted_within_days: int | None = Query(None, ge=1, le=365),
    min_match: int | None = Query(None, ge=0, le=100),
    sort: str = Query("relevance", pattern="^(relevance|date|salary|match)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    filters = {
        "q": q, "title": title, "company": company, "location": location, "skills": csv(skills), "work_mode": csv(work_mode),
        "employment_type": csv(employment_type), "experience_level": csv(experience_level), "category": category, "source": source,
        "salary_min": salary_min, "salary_max": salary_max, "posted_within_days": posted_within_days,
    }
    ctx = candidate_context(db, user)
    effective_sort = sort if (sort != "relevance" or q) else "date"
    if effective_sort == "match" and ctx is None:
        effective_sort = "relevance" if q else "date"
    saved_ids, applied = set(), {}
    if user is not None and user.role == "candidate" and user.candidate_profile:
        saved_ids = {r[0] for r in db.execute(select(SavedJob.job_id).where(SavedJob.candidate_id == user.candidate_profile.id))}
        applied = dict(db.execute(select(Application.job_id, Application.status).where(Application.candidate_id == user.candidate_profile.id)).all())
    needs_scoring = ctx is not None and (sort == "match" or min_match is not None)
    items, highlights = [], {}
    if needs_scoring:
        profile, snapshot, model = ctx
        signature = snapshot.signature()
        pool, _, highlights = search_service.run_search(db, filters, "relevance" if q else "date", 300, 0)
        scored = []
        for job in pool:
            result = matching.get_or_compute(db, profile, job, snapshot, model, signature)
            if min_match is not None and result["score"] < min_match:
                continue
            scored.append((job, result["score"]))
        db.commit()
        if sort == "match":
            scored.sort(key=lambda x: -x[1])
        total = len(scored)
        window = scored[(page - 1) * page_size: page * page_size]
        items = [job_dict(j, m, highlights.get(j.id), j.id in saved_ids, applied.get(j.id)) for j, m in window]
    else:
        jobs, total, highlights = search_service.run_search(db, filters, effective_sort, page_size, (page - 1) * page_size)
        scores = {}
        if ctx:
            profile, snapshot, model = ctx
            signature = snapshot.signature()
            for job in jobs:
                scores[job.id] = matching.get_or_compute(db, profile, job, snapshot, model, signature)["score"]
            db.commit()
        items = [job_dict(j, scores.get(j.id), highlights.get(j.id), j.id in saved_ids if user else None, applied.get(j.id)) for j in jobs]
    if user is not None and user.role == "candidate" and page == 1:
        search_service.record_search(db, user.id, q, filters, total)
        db.commit()
    return JobPage(items=items, total=total, page=page, page_size=page_size, pages=max(1, math.ceil(total / page_size)), sort=effective_sort, query=q)


@router.get("/suggestions")
def suggestions(q: str = Query("", max_length=80), db: Session = Depends(get_db)):
    return search_service.suggestions(db, q)


@router.get("/meta")
def meta(db: Session = Depends(get_db)):
    categories = [{"id": c.id, "name": c.name, "slug": c.slug} for c in db.scalars(select(JobCategory).order_by(JobCategory.name))]
    sources = [{"key": s.key, "name": s.name, "is_native": s.is_native} for s in db.scalars(select(JobSource).where(JobSource.enabled.is_(True)))]
    total = db.scalar(select(func.count()).select_from(Job).where(Job.status == "active")) or 0
    return {"categories": categories, "sources": sources, "active_jobs": total, "work_modes": ["remote", "onsite", "hybrid"], "employment_types": ["full_time", "part_time", "contract", "internship", "freelance", "temporary"], "experience_levels": ["Entry Level", "Junior", "Mid Level", "Senior", "Lead", "Executive"]}


@router.get("/{job_id}")
def job_detail(job_id: int, user: User | None = Depends(get_optional_user), db: Session = Depends(get_db)):
    job = job_service.get_job_or_404(db, job_id)
    privileged = False
    if user is not None:
        scope = company_scope(user)
        privileged = user.role == "admin" or (scope is not None and job.company_id == scope.id)
    if job.status in ("pending_review", "removed") and not privileged:
        raise HTTPException(404, "Job not found")
    saved, applied, match = None, None, None
    if user is not None and user.role == "candidate" and user.candidate_profile:
        profile = user.candidate_profile
        saved = bool(db.scalar(select(SavedJob.id).where(SavedJob.candidate_id == profile.id, SavedJob.job_id == job.id)))
        applied = db.scalar(select(Application.status).where(Application.candidate_id == profile.id, Application.job_id == job.id))
        snapshot = matching.build_candidate_snapshot(db, profile)
        if snapshot.has_profile_data:
            match = matching.get_or_compute(db, profile, job, snapshot)
    db.add(JobView(job_id=job.id, user_id=user.id if user and user.role == "candidate" else None))
    db.commit()
    data = job_dict(job, match["score"] if match else None, None, saved, applied, detail=True)
    data["match_details"] = match
    data["match_available"] = match is not None
    return data


@router.post("/{job_id}/save", status_code=201)
def save_job(job_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "candidate":
        raise HTTPException(403, "Only candidates can save jobs")
    job_service.get_job_or_404(db, job_id)
    profile = user.candidate_profile
    if not db.scalar(select(SavedJob.id).where(SavedJob.candidate_id == profile.id, SavedJob.job_id == job_id)):
        db.add(SavedJob(candidate_id=profile.id, job_id=job_id))
        db.commit()
    return {"saved": True}


@router.delete("/{job_id}/save")
def unsave_job(job_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "candidate":
        raise HTTPException(403, "Only candidates can save jobs")
    row = db.scalar(select(SavedJob).where(SavedJob.candidate_id == user.candidate_profile.id, SavedJob.job_id == job_id))
    if row:
        db.delete(row)
        db.commit()
    return {"saved": False}


@router.post("/{job_id}/report", status_code=201)
def report_job(job_id: int, data: ReportIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job_service.get_job_or_404(db, job_id)
    if db.scalar(select(Report.id).where(Report.job_id == job_id, Report.reporter_id == user.id, Report.status == "open")):
        raise HTTPException(409, "You have already reported this job")
    db.add(Report(job_id=job_id, reporter_id=user.id, reason=data.reason, details=data.details))
    audit(db, user.id, "job.report", "job", job_id, {"reason": data.reason})
    db.commit()
    return {"reported": True}


@companies.get("")
def list_companies(q: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=50), db: Session = Depends(get_db)):
    counts = select(Job.company_id.label("cid"), func.count().label("n")).where(Job.status == "active").group_by(Job.company_id).subquery()
    query = select(Company, func.coalesce(counts.c.n, 0)).outerjoin(counts, counts.c.cid == Company.id).where(func.coalesce(counts.c.n, 0) > 0)
    if q:
        query = query.where(Company.name.ilike(f"%{q}%"))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(query.order_by(func.coalesce(counts.c.n, 0).desc(), Company.name).offset((page - 1) * page_size).limit(page_size)).all()
    items = [{"id": c.id, "name": c.name, "slug": c.slug, "industry": c.industry, "location": c.location, "website": c.website, "verified": c.is_verified, "open_jobs": n, "description": (c.description or "")[:200]} for c, n in rows]
    return {"items": items, "total": total, "page": page, "page_size": page_size, "pages": max(1, math.ceil(total / page_size))}


@companies.get("/{company_id}")
def company_detail(company_id: int, db: Session = Depends(get_db)):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "Company not found")
    jobs = db.scalars(select(Job).options(selectinload(Job.skills), selectinload(Job.source), selectinload(Job.category), selectinload(Job.company)).where(Job.company_id == company.id, Job.status == "active").order_by(Job.published_at.desc()).limit(50)).all()
    return {"id": company.id, "name": company.name, "website": company.website, "industry": company.industry, "size": company.size, "location": company.location, "description": company.description, "verified": company.is_verified, "jobs": [job_dict(j) for j in jobs]}
