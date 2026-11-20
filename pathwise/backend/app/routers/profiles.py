from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.models import CandidatePreference, CandidateSkill, Company, EmployerProfile, RecruiterProfile, User
from app.schemas.profiles import (
    CandidateProfileIn,
    CandidateProfileOut,
    CompanyIn,
    CompanyOut,
    EmployerProfileIn,
    EmployerProfileOut,
    PreferencesIn,
    PreferencesOut,
    RecruiterProfileIn,
    RecruiterProfileOut,
)
from app.services.auth import unique_company_slug
from app.services.notifications import audit

candidates = APIRouter(prefix="/api/candidate", tags=["candidate"])
employers = APIRouter(prefix="/api/employer", tags=["employer"])
recruiters = APIRouter(prefix="/api/recruiter", tags=["recruiter"])


def completion(db: Session, profile) -> int:
    checks = [
        bool(profile.headline),
        bool(profile.summary),
        bool(profile.location),
        bool(profile.phone),
        profile.years_experience is not None,
        bool(profile.experience_level),
        bool(db.scalar(select(CandidateSkill.id).where(CandidateSkill.candidate_id == profile.id).limit(1))),
        bool(db.scalar(select(CandidatePreference.id).where(CandidatePreference.candidate_id == profile.id))),
    ]
    from app.models import Resume

    checks.append(bool(db.scalar(select(Resume.id).where(Resume.candidate_id == profile.id, Resume.is_active.is_(True)).limit(1))))
    return round(100 * sum(checks) / len(checks))


def candidate_out(db: Session, profile) -> CandidateProfileOut:
    out = CandidateProfileOut.model_validate(profile)
    out.completion = completion(db, profile)
    return out


@candidates.get("/profile", response_model=CandidateProfileOut)
def get_candidate_profile(user: User = Depends(require_roles("candidate")), db: Session = Depends(get_db)):
    return candidate_out(db, user.candidate_profile)


@candidates.put("/profile", response_model=CandidateProfileOut)
def update_candidate_profile(data: CandidateProfileIn, user: User = Depends(require_roles("candidate")), db: Session = Depends(get_db)):
    profile = user.candidate_profile
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    audit(db, user.id, "candidate.profile_update", "candidate_profile", profile.id)
    db.commit()
    return candidate_out(db, profile)


@candidates.get("/preferences", response_model=PreferencesOut)
def get_preferences(user: User = Depends(require_roles("candidate")), db: Session = Depends(get_db)):
    prefs = db.scalar(select(CandidatePreference).where(CandidatePreference.candidate_id == user.candidate_profile.id))
    return prefs or PreferencesOut()


@candidates.put("/preferences", response_model=PreferencesOut)
def update_preferences(data: PreferencesIn, user: User = Depends(require_roles("candidate")), db: Session = Depends(get_db)):
    profile = user.candidate_profile
    prefs = db.scalar(select(CandidatePreference).where(CandidatePreference.candidate_id == profile.id))
    if prefs is None:
        prefs = CandidatePreference(candidate_id=profile.id)
        db.add(prefs)
    for field, value in data.model_dump().items():
        setattr(prefs, field, value)
    db.commit()
    return prefs


def company_for(user: User) -> Company | None:
    return user.employer_profile.company if user.employer_profile else None


@employers.get("/profile", response_model=EmployerProfileOut)
def get_employer_profile(user: User = Depends(require_roles("employer")), db: Session = Depends(get_db)):
    return user.employer_profile


@employers.put("/profile", response_model=EmployerProfileOut)
def update_employer_profile(data: EmployerProfileIn, user: User = Depends(require_roles("employer")), db: Session = Depends(get_db)):
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user.employer_profile, field, value)
    db.commit()
    return user.employer_profile


@employers.get("/company", response_model=CompanyOut)
def get_company(user: User = Depends(require_roles("employer")), db: Session = Depends(get_db)):
    company = company_for(user)
    if company is None:
        raise HTTPException(404, "No company profile yet")
    return company


@employers.put("/company", response_model=CompanyOut)
def upsert_company(data: CompanyIn, user: User = Depends(require_roles("employer")), db: Session = Depends(get_db)):
    company = company_for(user)
    if company is None:
        company = Company(name=data.name.strip(), slug=unique_company_slug(db, data.name), created_by=user.id)
        db.add(company)
        db.flush()
        user.employer_profile.company_id = company.id
    for field, value in data.model_dump().items():
        setattr(company, field, value)
    audit(db, user.id, "company.upsert", "company", company.id)
    db.commit()
    return company


@recruiters.get("/profile", response_model=RecruiterProfileOut)
def get_recruiter_profile(user: User = Depends(require_roles("recruiter")), db: Session = Depends(get_db)):
    return user.recruiter_profile


@recruiters.put("/profile", response_model=RecruiterProfileOut)
def update_recruiter_profile(data: RecruiterProfileIn, user: User = Depends(require_roles("recruiter")), db: Session = Depends(get_db)):
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user.recruiter_profile, field, value)
    db.commit()
    return user.recruiter_profile
