from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import client_ip, get_current_user
from app.core.security import hash_password, verify_password
from app.models import User, UserSession
from app.schemas.auth import (
    AccountUpdateIn,
    ChangePasswordIn,
    ForgotPasswordIn,
    LoginIn,
    RegisterIn,
    ResetPasswordIn,
    TokenOut,
    UserOut,
    VerifyEmailIn,
)
from app.services import auth as service
from app.services.notifications import audit

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(data: RegisterIn, request: Request, db: Session = Depends(get_db)):
    return service.register_user(db, data, client_ip(request))


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, request: Request, db: Session = Depends(get_db)):
    user, token, expires = service.login_user(db, data.email, data.password, request.headers.get("user-agent"), client_ip(request))
    return TokenOut(access_token=token, expires_at=expires, user=UserOut.model_validate(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.core.security import decode_access_token

    token = request.headers["authorization"].split(" ", 1)[1]
    payload = decode_access_token(token)
    session = db.get(UserSession, payload["sid"])
    session.revoked = True
    audit(db, user.id, "user.logout", "user", user.id, None, client_ip(request))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/verify-email", status_code=status.HTTP_204_NO_CONTENT)
def verify_email(data: VerifyEmailIn, db: Session = Depends(get_db)):
    service.verify_email(db, data.token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/resend-verification", status_code=status.HTTP_204_NO_CONTENT)
def resend_verification(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.core.config import settings
    from app.core.security import hash_token, new_token
    from app.services.notifications import queue_email

    if not user.email_verified:
        token = new_token()
        user.verification_token_hash = hash_token(token)
        queue_email(db, user, "Verify your Pathwise email", f"Verify your email: {settings.frontend_url}/verify-email?token={token}")
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
def forgot_password(data: ForgotPasswordIn, db: Session = Depends(get_db)):
    service.request_password_reset(db, data.email)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(data: ResetPasswordIn, db: Session = Depends(get_db)):
    service.reset_password(db, data.token, data.password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=UserOut)
def update_me(data: AccountUpdateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if data.full_name:
        user.full_name = data.full_name.strip()
    if data.email_preferences:
        user.email_preferences = data.email_preferences.model_dump()
    db.commit()
    return user


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(data: ChangePasswordIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from fastapi import HTTPException

    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    user.password_hash = hash_password(data.new_password)
    audit(db, user.id, "user.password_change", "user", user.id, None, client_ip(request))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
