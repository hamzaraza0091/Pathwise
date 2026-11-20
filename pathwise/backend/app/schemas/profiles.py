from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

EXPERIENCE_LEVELS = Literal["Entry Level", "Junior", "Mid Level", "Senior", "Lead", "Executive"]


class CandidateProfileIn(BaseModel):
    headline: str | None = Field(default=None, max_length=255)
    summary: str | None = Field(default=None, max_length=5000)
    phone: str | None = Field(default=None, max_length=40)
    location: str | None = Field(default=None, max_length=255)
    years_experience: float | None = Field(default=None, ge=0, le=60)
    experience_level: EXPERIENCE_LEVELS | None = None
    linkedin_url: str | None = Field(default=None, max_length=500)
    portfolio_url: str | None = Field(default=None, max_length=500)
    resume_visible_to_employers: bool | None = None
    discoverable: bool | None = None
    ai_processing_consent: bool | None = None


class CandidateProfileOut(CandidateProfileIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    updated_at: datetime
    completion: int = 0


class PreferencesIn(BaseModel):
    desired_titles: list[str] = Field(default_factory=list, max_length=20)
    preferred_locations: list[str] = Field(default_factory=list, max_length=20)
    work_modes: list[Literal["remote", "onsite", "hybrid"]] = Field(default_factory=list)
    employment_types: list[str] = Field(default_factory=list, max_length=10)
    min_salary: float | None = Field(default=None, ge=0)
    salary_currency: str | None = Field(default=None, max_length=8)
    open_to_relocation: bool = False


class PreferencesOut(PreferencesIn):
    model_config = ConfigDict(from_attributes=True)


class CompanyIn(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    website: str | None = Field(default=None, max_length=500)
    industry: str | None = Field(default=None, max_length=120)
    size: str | None = Field(default=None, max_length=40)
    location: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    logo_url: str | None = Field(default=None, max_length=500)


class CompanyOut(CompanyIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    is_verified: bool


class EmployerProfileIn(BaseModel):
    job_title: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)


class EmployerProfileOut(EmployerProfileIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    company: CompanyOut | None = None


class RecruiterProfileIn(BaseModel):
    specialization: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)


class RecruiterProfileOut(RecruiterProfileIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    company_id: int | None = None
