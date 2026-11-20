import logging
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import AuditLog, EmailOutbox, Notification, User

logger = logging.getLogger("pathwise.email")

PREFERENCE_BY_KIND = {
    "new_recommendations": "new_recommendations",
    "high_match": "high_match_alerts",
    "application_update": "application_updates",
    "interview": "interview_invitations",
}


def audit(db: Session, user_id: int | None, action: str, entity_type: str | None = None, entity_id=None, detail=None, ip=None):
    db.add(AuditLog(user_id=user_id, action=action, entity_type=entity_type, entity_id=str(entity_id) if entity_id is not None else None, detail=detail, ip_address=ip))


def queue_email(db: Session, user: User, subject: str, body: str, kind: str | None = None):
    preference = PREFERENCE_BY_KIND.get(kind) if kind else None
    if preference and not (user.email_preferences or {}).get(preference, True):
        return None
    message = EmailOutbox(user_id=user.id, to_email=user.email, subject=subject, body=body)
    db.add(message)
    return message


def notify(db: Session, user: User, kind: str, title: str, body: str | None = None, link: str | None = None, email: bool = True):
    db.add(Notification(user_id=user.id, kind=kind, title=title, body=body, link=link))
    if email:
        queue_email(db, user, title, f"{body or title}\n\n{settings.frontend_url}{link or ''}", kind)


def deliver(message: EmailOutbox):
    if not settings.smtp_host:
        if settings.email_backend == "console":
            logger.info("EMAIL to=%s subject=%s\n%s", message.to_email, message.subject, message.body)
            return
        raise RuntimeError("SMTP is not configured")
    mail = EmailMessage()
    mail["From"] = settings.mail_from
    mail["To"] = message.to_email
    mail["Subject"] = message.subject
    mail.set_content(message.body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
        server.starttls()
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(mail)


def process_outbox(batch: int = 25, max_attempts: int | None = None) -> int:
    max_attempts = max_attempts or settings.email_max_attempts
    sent = 0
    with SessionLocal() as db:
        now = datetime.now(timezone.utc)
        pending = db.scalars(
            select(EmailOutbox)
            .where(EmailOutbox.status == "pending", EmailOutbox.next_attempt_at <= now)
            .order_by(EmailOutbox.id)
            .limit(batch)
        ).all()
        for message in pending:
            message.attempts += 1
            try:
                deliver(message)
                message.status = "sent"
                message.sent_at = now
                message.last_error = None
                sent += 1
            except Exception as error:
                message.last_error = str(error)[:500]
                if message.attempts >= max_attempts:
                    message.status = "failed"
                else:
                    message.next_attempt_at = now + timedelta(minutes=2 ** message.attempts)
            db.commit()
    return sent
