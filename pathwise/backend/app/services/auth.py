import re
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, hash_password, hash_token, new_token, verify_password
from app.models import CandidateProfile, Company, EmployerProfile, RecruiterProfile, User, UserSession
from app.models.users import utcnow
from app.services.notifications import audit, queue_email


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "company"


def unique_company_slug(db: Session, name: str) -> str:
    base = slugify(name)
    slug, counter = base, 2
    while db.scalar(select(Company.id).where(Company.slug == slug)):
        slug = f"{base}-{counter}"
        counter += 1
    return slug


def register_user(db: Session, data, ip: str | None) -> User:
    email = data.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    token = new_token()
    user = User(
        email=email,
        password_hash=hash_password(data.password),
        full_name=data.full_name.strip(),
        role=data.role,
        verification_token_hash=hash_token(token),
    )
    db.add(user)
    db.flush()
    if data.role == "candidate":
        db.add(CandidateProfile(user_id=user.id))
    elif data.role == "employer":
        company = None
        if data.company_name:
            company = Company(name=data.company_name.strip(), slug=unique_company_slug(db, data.company_name), created_by=user.id)
            db.add(company)
            db.flush()
        db.add(EmployerProfile(user_id=user.id, company_id=company.id if company else None))
    else:
        db.add(RecruiterProfile(user_id=user.id))
    queue_email(
        db,
        user,
        "Welcome to Pathwise - verify your email",
        f"Hi {user.full_name},\n\nVerify your email: {settings.frontend_url}/verify-email?token={token}",
    )
    audit(db, user.id, "user.register", "user", user.id, {"role": data.role}, ip)
    db.commit()
    return user


def create_session(db: Session, user: User, user_agent: str | None, ip: str | None):
    session = UserSession(
        user_id=user.id,
        expires_at=utcnow() + timedelta(minutes=settings.access_token_minutes),
        user_agent=(user_agent or "")[:255],
        ip_address=ip,
    )
    db.add(session)
    db.flush()
    token, expires = create_access_token(user.id, session.id)
    session.expires_at = expires
    user.last_login_at = utcnow()
    return token, expires


def login_user(db: Session, email: str, password: str, user_agent: str | None, ip: str | None):
    user = db.scalar(select(User).where(User.email == email.lower()))
    if user is None or not verify_password(password, user.password_hash):
        audit(db, user.id if user else None, "user.login_failed", "user", user.id if user else None, None, ip)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been deactivated")
    token, expires = create_session(db, user, user_agent, ip)
    audit(db, user.id, "user.login", "user", user.id, None, ip)
    db.commit()
    return user, token, expires


def verify_email(db: Session, token: str):
    user = db.scalar(select(User).where(User.verification_token_hash == hash_token(token)))
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired verification link")
    user.email_verified = True
    user.verification_token_hash = None
    db.commit()


def request_password_reset(db: Session, email: str):
    user = db.scalar(select(User).where(User.email == email.lower()))
    if user is None or not user.is_active:
        return
    token = new_token()
    user.reset_token_hash = hash_token(token)
    user.reset_token_expires = utcnow() + timedelta(hours=1)
    queue_email(db, user, "Reset your Pathwise password", f"Reset your password: {settings.frontend_url}/reset-password?token={token}\n\nThis link expires in one hour.")
    db.commit()


def reset_password(db: Session, token: str, password: str):
    user = db.scalar(select(User).where(User.reset_token_hash == hash_token(token)))
    expires = user.reset_token_expires if user else None
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if user is None or expires is None or expires < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired reset link")
    user.password_hash = hash_password(password)
    user.reset_token_hash = None
    user.reset_token_expires = None
    for session in db.scalars(select(UserSession).where(UserSession.user_id == user.id, UserSession.revoked.is_(False))):
        session.revoked = True
    audit(db, user.id, "user.password_reset", "user", user.id)
    db.commit()
