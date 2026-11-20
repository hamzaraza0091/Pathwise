from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

WorkMode = Literal["remote", "onsite", "hybrid"]
EmploymentType = Literal["full_time", "part_time", "contract", "internship", "freelance", "temporary"]
Level = Literal["Entry Level", "Junior", "Mid Level", "Senior", "Lead", "Executive"]
Education = Literal["high_school", "diploma", "bachelor", "master", "phd"]


class JobIn(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    description: str = Field(min_length=30, max_length=30000)
    location: str | None = Field(default=None, max_length=255)
    work_mode: WorkMode | None = None
    employment_type: EmploymentType = "full_time"
    experience_level: Level | None = None
    min_years: float | None = Field(default=None, ge=0, le=40)
    education_required: Education | None = None
    salary_min: float | None = Field(default=None, ge=0)
    salary_max: float | None = Field(default=None, ge=0)
    salary_currency: str | None = Field(default=None, max_length=8)
    salary_period: Literal["year", "month", "hour"] | None = None
    category: str | None = Field(default=None, max_length=120)
    required_skills: list[str] = Field(default_factory=list, max_length=40)
    preferred_skills: list[str] = Field(default_factory=list, max_length=40)
    application_url: str | None = Field(default=None, max_length=1000)
    expires_at: datetime | None = None

    @field_validator("application_url")
    @classmethod
    def http_url(cls, value):
        if value and not value.startswith(("http://", "https://")):
            raise ValueError("Application URL must start with http:// or https://")
        return value

    @model_validator(mode="after")
    def salary_order(self):
        if self.salary_min is not None and self.salary_max is not None and self.salary_min > self.salary_max:
            raise ValueError("Minimum salary cannot exceed maximum salary")
        return self


class JobUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=300)
    description: str | None = Field(default=None, min_length=30, max_length=30000)
    location: str | None = Field(default=None, max_length=255)
    work_mode: WorkMode | None = None
    employment_type: EmploymentType | None = None
    experience_level: Level | None = None
    min_years: float | None = Field(default=None, ge=0, le=40)
    education_required: Education | None = None
    salary_min: float | None = Field(default=None, ge=0)
    salary_max: float | None = Field(default=None, ge=0)
    salary_currency: str | None = Field(default=None, max_length=8)
    salary_period: Literal["year", "month", "hour"] | None = None
    category: str | None = Field(default=None, max_length=120)
    required_skills: list[str] | None = Field(default=None, max_length=40)
    preferred_skills: list[str] | None = Field(default=None, max_length=40)
    application_url: str | None = Field(default=None, max_length=1000)
    expires_at: datetime | None = None


class ReportIn(BaseModel):
    reason: Literal["scam", "misleading", "discriminatory", "duplicate", "expired", "other"]
    details: str | None = Field(default=None, max_length=1000)


class JobPage(BaseModel):
    items: list[dict]
    total: int
    page: int
    page_size: int
    pages: int
    sort: str
    query: str | None = None


class ApplyIn(BaseModel):
    cover_letter: str | None = Field(default=None, max_length=5000)
    resume_id: int | None = None


class StatusIn(BaseModel):
    status: Literal["viewed", "under_review", "shortlisted", "interview_scheduled", "offer", "rejected"]
    note: str | None = Field(default=None, max_length=500)


class InterviewIn(BaseModel):
    scheduled_at: datetime
    duration_minutes: int = Field(default=30, ge=10, le=480)
    mode: Literal["video", "phone", "onsite"] = "video"
    location_or_link: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=2000)


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=3000)


class SkillIn(BaseModel):
    skill: str = Field(min_length=1, max_length=120)
    kind: Literal["technical", "soft"] = "technical"


class EducationIn(BaseModel):
    degree: str = Field(min_length=2, max_length=255)
    level: Literal["high_school", "diploma", "bachelor", "master", "phd", "none"] = "bachelor"
    institution: str | None = Field(default=None, max_length=255)
    field_of_study: str | None = Field(default=None, max_length=255)
    end_year: int | None = Field(default=None, ge=1950, le=2100)


class ExperienceIn(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    company: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=3000)
    start_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    end_date: str | None = Field(default=None, pattern=r"^(\d{4}-\d{2}|present)$")
    months: int | None = Field(default=None, ge=0, le=720)


class NamedIn(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=1500)


class ShortlistIn(BaseModel):
    candidate_id: int
    job_id: int | None = None
    note: str | None = Field(default=None, max_length=500)


class RecruiterAttachIn(BaseModel):
    email: str
