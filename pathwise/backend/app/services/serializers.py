from app.models import Application, Job
from app.services.normalize import aware


def iso(value):
    value = aware(value)
    return value.isoformat() if value else None


def job_dict(job: Job, match: float | None = None, highlight: dict | None = None, saved: bool | None = None, applied: str | None = None, detail: bool = False) -> dict:
    native = job.is_native_job
    source = job.source
    data = {
        "id": job.id, "title": job.title, "company": {"id": job.company_id, "name": job.company_name, "verified": bool(job.company and job.company.is_verified)},
        "company_name": job.company_name, "location": job.location, "work_mode": job.work_mode, "employment_type": job.employment_type,
        "experience_level": job.experience_level, "min_years": job.min_years, "education_required": job.education_required,
        "salary": {"min": job.salary_min, "max": job.salary_max, "currency": job.salary_currency, "period": job.salary_period} if (job.salary_min or job.salary_max) else None,
        "category": job.category.name if job.category else None,
        "skills": {"required": sorted(s.skill for s in job.skills if s.is_required), "preferred": sorted(s.skill for s in job.skills if not s.is_required)},
        "source": {"key": source.key, "name": source.name, "is_native": native, "url": source.base_url},
        "attribution": None if native else f"Originally posted on {source.name}",
        "apply_mode": "native" if native else "external",
        "apply_url": None if native else (job.application_url or job.original_url),
        "original_url": None if native else job.original_url,
        "published_at": iso(job.published_at), "expires_at": iso(job.expires_at), "first_imported_at": iso(job.first_imported_at), "status": job.status,
        "match": None if match is None else round(match),
        "saved": saved, "application_status": applied,
    }
    if detail:
        data["description"] = job.description
    else:
        data["excerpt"] = (job.description or "")[:280]
    if highlight:
        data["highlight"] = highlight
    return data


def application_dict(app: Application, include_candidate: bool = False, viewer_company: bool = False) -> dict:
    data = {
        "id": app.id, "status": app.status, "match_score": None if app.match_score is None else round(app.match_score),
        "cover_letter": app.cover_letter, "created_at": iso(app.created_at), "updated_at": iso(app.updated_at),
        "job": {"id": app.job.id, "title": app.job.title, "company_name": app.job.company_name, "location": app.job.location},
        "history": [{"from": h.from_status, "to": h.to_status, "note": h.note, "at": iso(h.created_at)} for h in app.history],
        "interviews": [{"id": i.id, "scheduled_at": iso(i.scheduled_at), "duration_minutes": i.duration_minutes, "mode": i.mode, "location_or_link": i.location_or_link, "notes": i.notes, "status": i.status} for i in app.interviews],
        "has_resume": app.resume_id is not None,
    }
    if include_candidate:
        profile = app.candidate_profile_rel
        data["candidate"] = {"id": profile.id, "name": profile.user.full_name, "email": profile.user.email, "headline": profile.headline, "location": profile.location, "years_experience": profile.years_experience, "phone": profile.phone}
    return data
