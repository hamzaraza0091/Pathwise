from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=255)
    role: Literal["candidate", "employer", "recruiter"]
    company_name: str | None = Field(default=None, max_length=255)

    @field_validator("password")
    @classmethod
    def strong_password(cls, value):
        if not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
            raise ValueError("Password must contain letters and numbers")
        return value


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class VerifyEmailIn(BaseModel):
    token: str


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: str
    is_active: bool
    email_verified: bool
    email_preferences: dict
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserOut


class EmailPreferencesIn(BaseModel):
    new_recommendations: bool = True
    high_match_alerts: bool = True
    application_updates: bool = True
    interview_invitations: bool = True


class AccountUpdateIn(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    email_preferences: EmailPreferencesIn | None = None
