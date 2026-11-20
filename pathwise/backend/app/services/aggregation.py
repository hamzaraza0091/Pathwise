import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.adapters.base import Adapter, RawJob, SourceError
from app.adapters.sources import ADAPTERS
from app.core.config import settings
from app.models import Company, ExternalJobRecord, IngestionLog, Job, JobSource, SourceSyncRun
from app.models.users import utcnow
from app.services import jobs as job_service
from app.services.auth import unique_company_slug
from app.services.normalize import (
    aware, clean_title, content_hash, dedupe_hash, extract_education_required, extract_min_years, html_to_text, infer_level,
    infer_work_mode, map_category, map_employment_type, normalize_key, parse_salary, to_utc,
)
from app.services.skills import classify_job_skills

logger = logging.getLogger("pathwise.aggregation")
STALE_GRACE = timedelta(days=3)


def seed_sources(db: Session):
    for key, cls in ADAPTERS.items():
        if key == "rss":
            continue
        if db.scalar(select(JobSource).where(JobSource.key == key)) is None:
            db.add(JobSource(key=key, name=cls.name, base_url=cls.base_url, refresh_minutes=cls.default_refresh_minutes, enabled=not cls.requires_credentials, config={"terms_url": cls.terms_url, "min_refresh_minutes": cls.min_refresh_minutes}))
    db.commit()


def adapter_for(source: JobSource) -> Adapter:
    kind = source.config.get("adapter", source.key) if source.config else source.key
    cls = ADAPTERS.get(kind)
    if cls is None:
        raise SourceError(f"No adapter available for source '{source.key}'")
    adapter = cls(source.config or {})
    return adapter


def log(db: Session, run: SourceSyncRun, level: str, message: str):
    db.add(IngestionLog(sync_run_id=run.id, level=level, message=message[:1000]))


def external_company(db: Session, name: str, cache: dict) -> Company:
    key = normalize_key(name)
    if key in cache:
        return cache[key]
    company = db.scalar(select(Company).where(Company.is_external.is_(True), Company.name == name))
    if company is None:
        company = Company(name=name[:255], slug=unique_company_slug(db, name), is_external=True)
        db.add(company)
        db.flush()
    cache[key] = company
    return company


def normalize_raw(db: Session, raw: RawJob) -> dict | None:
    title = clean_title(raw.title)
    company = (raw.company or "").strip()
    description = html_to_text(raw.description)
    url = (raw.url or raw.apply_url or "").strip()
    if len(title) < 3 or not company or len(description) < 30 or not url.startswith(("http://", "https://")):
        return None
    work_mode = infer_work_mode(raw.location, title, description, raw.remote)
    lo, hi, currency = parse_salary(raw.salary_text, raw.salary_min, raw.salary_max, raw.salary_currency)
    tags = [t for t in (raw.tags or []) if isinstance(t, str)]
    required, preferred = classify_job_skills(db, f"{title}\n{description}", tags)
    published = to_utc(raw.published_at) or utcnow().replace(tzinfo=timezone.utc)
    location = (raw.location or "").strip() or ("Worldwide" if work_mode == "remote" else None)
    return {
        "title": title, "company": company[:255], "description": description, "location": location[:255] if location else None,
        "work_mode": work_mode, "employment_type": map_employment_type(raw.employment_type, title),
        "experience_level": infer_level(title, description, raw.level), "min_years": extract_min_years(description),
        "education_required": extract_education_required(description), "salary_min": lo, "salary_max": hi, "salary_currency": currency,
        "category": map_category(title, raw.category), "required": required, "preferred": preferred, "published_at": published,
        "expires_at": to_utc(raw.expires_at), "url": url, "apply_url": (raw.apply_url or url)[:1000],
    }


def apply_normalized(job: Job, n: dict):
    job.title, job.description, job.location, job.work_mode = n["title"], n["description"], n["location"], n["work_mode"]
    job.employment_type, job.experience_level, job.min_years = n["employment_type"], n["experience_level"], n["min_years"]
    job.education_required, job.salary_min, job.salary_max, job.salary_currency = n["education_required"], n["salary_min"], n["salary_max"], n["salary_currency"]
    job.original_url, job.application_url = n["url"][:1000], n["apply_url"]


def ingest(db: Session, source: JobSource, adapter: Adapter, client: httpx.Client, triggered_by: str = "scheduler", force: bool = False) -> SourceSyncRun:
    run = SourceSyncRun(source_id=source.id, triggered_by=triggered_by)
    db.add(run)
    db.commit()
    started = utcnow()
    min_gap = max(source.refresh_minutes or 0, adapter.min_refresh_minutes)
    last = aware(source.last_synced_at)
    if not force and last and datetime.now(timezone.utc) - last < timedelta(minutes=min_gap):
        run.status = "skipped"
        run.error = f"Respecting source update frequency (every {min_gap} minutes)"
        run.finished_at = utcnow()
        db.commit()
        return run
    try:
        if not adapter.configured():
            raise SourceError("Source credentials are not configured")
        raws = adapter.fetch(client)
    except Exception as error:
        db.rollback()
        run = db.get(SourceSyncRun, run.id)
        source = db.get(JobSource, source.id)
        run.status, run.error, run.finished_at = "failed", str(error)[:900], utcnow()
        source.last_synced_at = utcnow() if "rate limit" in str(error).lower() else source.last_synced_at
        source.config = (source.config or {}) | {"last_error": str(error)[:300]}
        log(db, run, "error", f"Fetch failed: {error}")
        db.commit()
        logger.warning("ingest %s failed: %s", source.key, error)
        return run
    run.fetched = len(raws)
    companies: dict = {}
    seen_ids = set()
    for raw in raws:
        try:
            with db.begin_nested():
                n = normalize_raw(db, raw)
                if n is None or not raw.external_id:
                    run.rejected += 1
                    log(db, run, "warning", f"Rejected invalid listing {raw.external_id!r}")
                    continue
                external_id = str(raw.external_id)[:200]
                seen_ids.add(external_id)
                chash = content_hash(n["title"], n["company"], n["description"][:2000], n["location"], n["salary_max"])
                record = db.scalar(select(ExternalJobRecord).where(ExternalJobRecord.source_id == source.id, ExternalJobRecord.external_id == external_id))
                existing = db.scalar(select(Job).options(selectinload(Job.skills)).where(Job.source_id == source.id, Job.external_id == external_id))
                now = utcnow()
                if existing is not None:
                    existing.last_seen_at = now
                    if record:
                        record.last_seen_at = now
                    if record is None or record.payload_hash != chash:
                        apply_normalized(existing, n)
                        existing.category_id = job_service.get_category(db, n["category"]).id
                        existing.dedupe_hash = dedupe_hash(n["title"], n["company"], n["location"], n["work_mode"] == "remote")
                        job_service.set_job_skills(existing, n["required"], n["preferred"])
                        job_service.set_job_location(existing)
                        job_service.embed_job(existing)
                        run.updated += 1
                        if record:
                            record.payload_hash = chash
                    if existing.status == "expired" and (existing.expires_at is None or aware(existing.expires_at) > now.replace(tzinfo=timezone.utc)):
                        existing.status = "active"
                    db.flush()
                    job_service.index_job(db, existing)
                    continue
                dh = dedupe_hash(n["title"], n["company"], n["location"], n["work_mode"] == "remote")
                twin = db.scalar(select(Job).where(Job.dedupe_hash == dh, Job.status == "active"))
                if twin is not None:
                    twin.last_seen_at = now
                    if record is None:
                        db.add(ExternalJobRecord(source_id=source.id, external_id=external_id, job_id=twin.id, payload_hash=chash))
                    run.duplicates += 1
                    continue
                company = external_company(db, n["company"], companies)
                published = n["published_at"]
                job = Job(
                    title=n["title"], company_id=company.id, company_name=n["company"], description=n["description"],
                    category_id=job_service.get_category(db, n["category"]).id, employment_type=n["employment_type"], experience_level=n["experience_level"],
                    work_mode=n["work_mode"], location=n["location"], salary_min=n["salary_min"], salary_max=n["salary_max"], salary_currency=n["salary_currency"],
                    salary_period="year" if n["salary_max"] and n["salary_max"] > 1000 else None, min_years=n["min_years"], education_required=n["education_required"],
                    source_id=source.id, external_id=external_id, original_url=n["url"][:1000], application_url=n["apply_url"], status="active",
                    dedupe_hash=dh, published_at=published, expires_at=n["expires_at"] or published + timedelta(days=settings.job_default_ttl_days),
                    first_imported_at=now, last_seen_at=now,
                )
                if job.expires_at and aware(job.expires_at) < datetime.now(timezone.utc):
                    job.status = "expired"
                db.add(job)
                db.flush()
                job_service.set_job_skills(job, n["required"], n["preferred"])
                job_service.set_job_location(job)
                job_service.embed_job(job)
                db.flush()
                job_service.index_job(db, job)
                if record is None:
                    db.add(ExternalJobRecord(source_id=source.id, external_id=external_id, job_id=job.id, payload_hash=chash))
                run.created += 1
        except Exception as error:
            run.rejected += 1
            log(db, run, "error", f"Failed to process {raw.external_id!r}: {error}")
            logger.exception("ingest row failed")
    if run.fetched > 0 and run.rejected < run.fetched:
        cutoff = utcnow() - STALE_GRACE
        stale = db.scalars(select(Job).options(selectinload(Job.skills)).where(Job.source_id == source.id, Job.status == "active", Job.last_seen_at < cutoff))
        for job in stale:
            job_service.set_job_status(db, job, "expired")
            run.expired += 1
    run.status = "success" if run.rejected < max(1, run.fetched) else "failed"
    run.finished_at = utcnow()
    source.last_synced_at = utcnow()
    source.config = {k: v for k, v in (source.config or {}).items() if k != "last_error"}
    log(db, run, "info", f"Fetched {run.fetched}: {run.created} new, {run.updated} updated, {run.duplicates} duplicates, {run.rejected} rejected, {run.expired} expired")
    db.commit()
    return run


def sync_source(db: Session, source: JobSource, client: httpx.Client | None = None, triggered_by: str = "scheduler", force: bool = False) -> SourceSyncRun:
    adapter = adapter_for(source)
    owns = client is None
    client = client or httpx.Client(follow_redirects=True)
    try:
        return ingest(db, source, adapter, client, triggered_by, force)
    finally:
        if owns:
            client.close()


def due_sources(db: Session) -> list[JobSource]:
    now = datetime.now(timezone.utc)
    due = []
    for source in db.scalars(select(JobSource).where(JobSource.enabled.is_(True), JobSource.is_native.is_(False))):
        try:
            adapter = adapter_for(source)
        except SourceError:
            continue
        gap = timedelta(minutes=max(source.refresh_minutes or 0, adapter.min_refresh_minutes))
        last = aware(source.last_synced_at)
        if last is None or now - last >= gap:
            due.append(source)
    return due
