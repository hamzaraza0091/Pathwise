import re

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.database import SessionLocal, get_db
from app.core.deps import require_roles
from app.models import AuditLog, Company, IngestionLog, Job, JobCategory, JobSource, MatchingModelVersion, Report, Skill, SourceSyncRun, SystemSetting, User
from app.models.users import utcnow
from app.schemas.auth import UserOut
from app.services import aggregation, analytics, jobs as job_service, matching, worker
from app.services.notifications import audit
from app.services.serializers import iso, job_dict

router = APIRouter(prefix="/api/admin", tags=["admin"])


class UserPage(BaseModel):
    items: list[UserOut]
    total: int
    page: int
    page_size: int


class UserAdminUpdate(BaseModel):
    is_active: bool | None = None
    role: str | None = None


@router.get("/users", response_model=UserPage)
def list_users(
    q: str | None = None,
    role: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    query = select(User)
    if q:
        like = f"%{q.lower()}%"
        query = query.where(or_(func.lower(User.email).like(like), func.lower(User.full_name).like(like)))
    if role:
        query = query.where(User.role == role)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(User.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return UserPage(items=items, total=total, page=page, page_size=page_size)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, data: UserAdminUpdate, admin: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if user.id == admin.id:
        raise HTTPException(400, "Administrators cannot modify their own account here")
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.role is not None:
        if data.role not in {"candidate", "employer", "recruiter", "admin"}:
            raise HTTPException(400, "Unknown role")
        user.role = data.role
    audit(db, admin.id, "admin.user_update", "user", user.id, data.model_dump(exclude_none=True))
    db.commit()
    return user


@router.get("/audit-logs")
def audit_logs(limit: int = Query(50, ge=1, le=200), admin: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)).all()
    return [
        {"id": r.id, "user_id": r.user_id, "action": r.action, "entity_type": r.entity_type, "entity_id": r.entity_id, "detail": r.detail, "created_at": r.created_at}
        for r in rows
    ]


admin_only = require_roles("admin")


@router.get("/analytics")
def platform_analytics(admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    return analytics.admin_stats(db)


@router.get("/jobs")
def admin_jobs(
    q: str | None = None,
    status: str | None = None,
    source: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    admin: User = Depends(admin_only),
    db: Session = Depends(get_db),
):
    query = select(Job).options(selectinload(Job.skills), selectinload(Job.source), selectinload(Job.category), selectinload(Job.company))
    if q:
        like = f"%{q.lower()}%"
        query = query.where(or_(func.lower(Job.title).like(like), func.lower(Job.company_name).like(like)))
    if status:
        query = query.where(Job.status == status)
    if source:
        query = query.join(JobSource, JobSource.id == Job.source_id).where(JobSource.key == source)
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    rows = db.scalars(query.order_by(Job.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [job_dict(j) for j in rows], "total": total, "page": page, "page_size": page_size}


class JobStatusIn(BaseModel):
    status: str
    note: str | None = None


@router.post("/jobs/{job_id}/status")
def admin_job_status(job_id: int, data: JobStatusIn, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    if data.status not in {"active", "closed", "removed", "pending_review"}:
        raise HTTPException(400, "Unsupported status")
    job = job_service.get_job_or_404(db, job_id)
    job_service.set_job_status(db, job, data.status)
    audit(db, admin.id, "admin.job_status", "job", job.id, {"status": data.status, "note": data.note})
    db.commit()
    return job_dict(job)


@router.get("/reports")
def list_reports(status: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    query = select(Report)
    if status:
        query = query.where(Report.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(Report.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    items = []
    for r in rows:
        job = db.get(Job, r.job_id)
        reporter = db.get(User, r.reporter_id) if r.reporter_id else None
        items.append({
            "id": r.id, "job_id": r.job_id, "job_title": job.title if job else None, "job_status": job.status if job else None,
            "company_name": job.company_name if job else None, "reason": r.reason, "details": r.details, "status": r.status,
            "resolution": r.resolution, "reporter": reporter.email if reporter else None, "created_at": iso(r.created_at), "resolved_at": iso(r.resolved_at),
        })
    return {"items": items, "total": total, "page": page, "page_size": page_size}


class ReportResolve(BaseModel):
    action: str
    resolution: str | None = None


@router.post("/reports/{report_id}/resolve")
def resolve_report(report_id: int, data: ReportResolve, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    if data.action not in {"remove_job", "dismiss"}:
        raise HTTPException(400, "Action must be remove_job or dismiss")
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(404, "Report not found")
    if report.status != "open":
        raise HTTPException(409, "Report already resolved")
    if data.action == "remove_job":
        job = job_service.get_job_or_404(db, report.job_id)
        job_service.set_job_status(db, job, "removed")
        for other in db.scalars(select(Report).where(Report.job_id == job.id, Report.status == "open")):
            other.status, other.resolved_by, other.resolved_at, other.resolution = "resolved", admin.id, utcnow(), data.resolution or "Job removed"
    else:
        report.status, report.resolved_by, report.resolved_at, report.resolution = "dismissed", admin.id, utcnow(), data.resolution or "Dismissed"
    audit(db, admin.id, "admin.report_resolve", "report", report.id, {"action": data.action})
    db.commit()
    return {"resolved": True}


@router.get("/companies")
def admin_companies(q: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    query = select(Company).where(Company.is_external.is_(False))
    if q:
        query = query.where(func.lower(Company.name).like(f"%{q.lower()}%"))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(Company.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    counts = dict(db.execute(select(Job.company_id, func.count()).where(Job.status == "active").group_by(Job.company_id)).all())
    items = [{"id": c.id, "name": c.name, "slug": c.slug, "website": c.website, "industry": c.industry, "is_verified": c.is_verified, "active_jobs": counts.get(c.id, 0)} for c in rows]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


class CompanyVerify(BaseModel):
    is_verified: bool


@router.patch("/companies/{company_id}")
def verify_company(company_id: int, data: CompanyVerify, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "Company not found")
    company.is_verified = data.is_verified
    audit(db, admin.id, "admin.company_verify", "company", company.id, {"is_verified": data.is_verified})
    db.commit()
    return {"id": company.id, "is_verified": company.is_verified}


def source_dict(db: Session, s: JobSource) -> dict:
    last = db.scalar(select(SourceSyncRun).where(SourceSyncRun.source_id == s.id).order_by(SourceSyncRun.id.desc()).limit(1))
    active = db.scalar(select(func.count()).select_from(Job).where(Job.source_id == s.id, Job.status == "active")) or 0
    try:
        adapter = aggregation.adapter_for(s)
        min_refresh, needs_credentials, configured = adapter.min_refresh_minutes, adapter.requires_credentials, adapter.configured()
    except Exception:
        min_refresh, needs_credentials, configured = None, False, True
    return {
        "id": s.id, "key": s.key, "name": s.name, "base_url": s.base_url, "is_native": s.is_native, "enabled": s.enabled,
        "refresh_minutes": s.refresh_minutes, "min_refresh_minutes": min_refresh, "last_synced_at": iso(s.last_synced_at), "active_jobs": active,
        "requires_credentials": needs_credentials, "configured": configured, "terms_url": (s.config or {}).get("terms_url"),
        "last_run": None if last is None else {"id": last.id, "status": last.status, "fetched": last.fetched, "created": last.created, "updated": last.updated, "duplicates": last.duplicates, "rejected": last.rejected, "expired": last.expired, "error": last.error, "started_at": iso(last.started_at), "finished_at": iso(last.finished_at)},
    }


@router.get("/sources")
def list_sources(admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    aggregation.seed_sources(db)
    return [source_dict(db, s) for s in db.scalars(select(JobSource).order_by(JobSource.id))]


class SourceUpdate(BaseModel):
    enabled: bool | None = None
    refresh_minutes: int | None = Field(None, ge=1, le=10080)


@router.patch("/sources/{source_id}")
def update_source(source_id: int, data: SourceUpdate, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    source = db.get(JobSource, source_id)
    if source is None or source.is_native:
        raise HTTPException(404, "Source not found")
    if data.enabled is not None:
        if data.enabled:
            adapter = aggregation.adapter_for(source)
            if not adapter.configured():
                raise HTTPException(400, "This source needs API credentials before it can be enabled")
        source.enabled = data.enabled
    if data.refresh_minutes is not None:
        adapter = aggregation.adapter_for(source)
        if data.refresh_minutes < adapter.min_refresh_minutes:
            raise HTTPException(400, f"{source.name} allows refreshing at most every {adapter.min_refresh_minutes} minutes")
        source.refresh_minutes = data.refresh_minutes
    audit(db, admin.id, "admin.source_update", "source", source.id, data.model_dump(exclude_none=True))
    db.commit()
    return source_dict(db, source)


def _sync_in_background(source_id: int, force: bool):
    with SessionLocal() as db:
        source = db.get(JobSource, source_id)
        if source is not None:
            try:
                aggregation.sync_source(db, source, triggered_by="admin", force=force)
            except Exception:
                db.rollback()


@router.post("/sources/{source_id}/sync", status_code=202)
def sync_now(source_id: int, tasks: BackgroundTasks, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    source = db.get(JobSource, source_id)
    if source is None or source.is_native:
        raise HTTPException(404, "Source not found")
    adapter = aggregation.adapter_for(source)
    if not adapter.configured():
        raise HTTPException(400, "This source needs API credentials before it can sync")
    audit(db, admin.id, "admin.source_sync", "source", source.id)
    db.commit()
    tasks.add_task(_sync_in_background, source.id, False)
    return {"queued": True}


@router.get("/sync-runs")
def sync_runs(source_id: int | None = None, limit: int = Query(30, ge=1, le=200), admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    query = select(SourceSyncRun, JobSource.name).join(JobSource, JobSource.id == SourceSyncRun.source_id)
    if source_id:
        query = query.where(SourceSyncRun.source_id == source_id)
    rows = db.execute(query.order_by(SourceSyncRun.id.desc()).limit(limit)).all()
    return [
        {"id": r.id, "source": name, "status": r.status, "fetched": r.fetched, "created": r.created, "updated": r.updated, "duplicates": r.duplicates, "rejected": r.rejected, "expired": r.expired, "error": r.error, "triggered_by": r.triggered_by, "started_at": iso(r.started_at), "finished_at": iso(r.finished_at)}
        for r, name in rows
    ]


@router.get("/sync-runs/{run_id}/logs")
def run_logs(run_id: int, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    rows = db.scalars(select(IngestionLog).where(IngestionLog.sync_run_id == run_id).order_by(IngestionLog.id)).all()
    return [{"id": r.id, "level": r.level, "message": r.message, "created_at": iso(r.created_at)} for r in rows]


class CategoryIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


@router.get("/categories")
def list_categories(admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    counts = dict(db.execute(select(Job.category_id, func.count()).group_by(Job.category_id)).all())
    return [{"id": c.id, "name": c.name, "slug": c.slug, "jobs": counts.get(c.id, 0)} for c in db.scalars(select(JobCategory).order_by(JobCategory.name))]


@router.post("/categories", status_code=201)
def create_category(data: CategoryIn, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    name = data.name.strip()
    if db.scalar(select(JobCategory).where(func.lower(JobCategory.name) == name.lower())):
        raise HTTPException(409, "Category already exists")
    category = JobCategory(name=name, slug=slugify(name))
    db.add(category)
    audit(db, admin.id, "admin.category_create", "category", None, {"name": name})
    db.commit()
    return {"id": category.id, "name": category.name, "slug": category.slug, "jobs": 0}


@router.put("/categories/{category_id}")
def rename_category(category_id: int, data: CategoryIn, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    category = db.get(JobCategory, category_id)
    if category is None:
        raise HTTPException(404, "Category not found")
    category.name, category.slug = data.name.strip(), slugify(data.name)
    audit(db, admin.id, "admin.category_rename", "category", category.id, {"name": category.name})
    db.commit()
    return {"id": category.id, "name": category.name, "slug": category.slug}


@router.delete("/categories/{category_id}", status_code=204)
def delete_category(category_id: int, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    category = db.get(JobCategory, category_id)
    if category is None:
        raise HTTPException(404, "Category not found")
    if db.scalar(select(func.count()).select_from(Job).where(Job.category_id == category.id)):
        raise HTTPException(409, "Category is in use by jobs")
    db.delete(category)
    audit(db, admin.id, "admin.category_delete", "category", category_id)
    db.commit()


class SkillIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: str = "technical"
    aliases: list[str] = []
    is_active: bool = True


def skill_dict(s: Skill) -> dict:
    return {"id": s.id, "name": s.name, "kind": s.kind, "aliases": s.aliases or [], "is_active": s.is_active}


@router.get("/skills")
def list_skills(q: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    query = select(Skill)
    if q:
        query = query.where(func.lower(Skill.name).like(f"%{q.lower()}%"))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(Skill.name).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [skill_dict(s) for s in rows], "total": total, "page": page, "page_size": page_size}


@router.post("/skills", status_code=201)
def create_skill(data: SkillIn, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    if data.kind not in {"technical", "soft"}:
        raise HTTPException(400, "Kind must be technical or soft")
    if db.scalar(select(Skill).where(func.lower(Skill.name) == data.name.strip().lower())):
        raise HTTPException(409, "Skill already exists")
    skill = Skill(name=data.name.strip(), kind=data.kind, aliases=[a.strip() for a in data.aliases if a.strip()], is_active=data.is_active)
    db.add(skill)
    audit(db, admin.id, "admin.skill_create", "skill", None, {"name": skill.name})
    db.commit()
    return skill_dict(skill)


@router.put("/skills/{skill_id}")
def update_skill(skill_id: int, data: SkillIn, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    skill = db.get(Skill, skill_id)
    if skill is None:
        raise HTTPException(404, "Skill not found")
    skill.name, skill.kind, skill.aliases, skill.is_active = data.name.strip(), data.kind, [a.strip() for a in data.aliases if a.strip()], data.is_active
    audit(db, admin.id, "admin.skill_update", "skill", skill.id)
    db.commit()
    return skill_dict(skill)


@router.delete("/skills/{skill_id}", status_code=204)
def delete_skill(skill_id: int, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    skill = db.get(Skill, skill_id)
    if skill is None:
        raise HTTPException(404, "Skill not found")
    db.delete(skill)
    audit(db, admin.id, "admin.skill_delete", "skill", skill_id)
    db.commit()


class SettingIn(BaseModel):
    value: dict


@router.get("/settings")
def get_settings(admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    rows = {r.key: r.value for r in db.scalars(select(SystemSetting))}
    model = matching.active_model(db)
    rows["matching_weights"] = {"weights": model.weights, "version": model.version}
    return rows


@router.put("/settings/{key}")
def put_setting(key: str, data: SettingIn, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    if key not in {"matching_weights", "announcement", "registration"}:
        raise HTTPException(400, "Unknown setting")
    if key == "matching_weights":
        weights = data.value.get("weights", {})
        expected = {"skills", "experience", "education", "location", "semantic", "preferences"}
        if set(weights) != expected or any(not isinstance(v, (int, float)) or v < 0 for v in weights.values()) or abs(sum(weights.values()) - 1) > 0.001:
            raise HTTPException(400, "Weights must cover all six dimensions and sum to 1")
    if key == "matching_weights":
        current = matching.active_model(db)
        current.is_active = False
        count = db.scalar(select(func.count()).select_from(MatchingModelVersion)) or 0
        db.add(MatchingModelVersion(version=f"v{count + 1}", weights={k: float(v) for k, v in weights.items()}, is_active=True))
    else:
        row = db.get(SystemSetting, key)
        if row is None:
            db.add(SystemSetting(key=key, value=data.value))
        else:
            row.value = data.value
    audit(db, admin.id, "admin.setting_update", "setting", key)
    db.commit()
    return {"key": key, "value": data.value}


@router.post("/maintenance/expire-jobs")
def expire_jobs(admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    return {"expired": job_service.expire_stale_jobs(db)}


@router.post("/maintenance/reindex")
def reindex(admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    return {"indexed": job_service.reindex_all(db)}


@router.post("/maintenance/backup")
def backup(admin: User = Depends(admin_only)):
    path = worker.run_backup()
    return {"backup": path.name if path else None}
