import logging
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.models import CandidatePreference, CandidateProfile, RecommendationHistory, User
from app.models.users import utcnow
from app.services import aggregation, jobs as job_service, notifications, recommendations, resume as resume_service
from app.services.normalize import aware

logger = logging.getLogger("pathwise.worker")
_stop = threading.Event()
_state = {"last_alerts": time.time(), "last_expiry": 0.0, "last_backup": 0.0}


def run_ingestion():
    with SessionLocal() as db:
        for source in aggregation.due_sources(db):
            try:
                aggregation.sync_source(db, source, triggered_by="scheduler")
            except Exception:
                db.rollback()
                logger.exception("ingestion crashed for %s", source.key)


def run_job_alerts() -> int:
    sent = 0
    with SessionLocal() as db:
        profiles = db.scalars(select(CandidateProfile).join(User, User.id == CandidateProfile.user_id).where(User.is_active.is_(True), User.role == "candidate"))
        for profile in profiles:
            user = profile.user
            prefs = user.email_preferences or {}
            if not (prefs.get("high_match_alerts", True) or prefs.get("new_recommendations", True)):
                continue
            ranked = recommendations.rank(db, profile, limit=200)
            if not ranked:
                continue
            already = {r[0] for r in db.execute(select(RecommendationHistory.job_id).where(RecommendationHistory.candidate_id == profile.id))}
            fresh = [r for r in ranked if r["job"].id not in already]
            high = [r for r in fresh if r["match"] >= settings.high_match_threshold]
            recommendations.persist_batch(db, profile, ranked)
            if high and prefs.get("high_match_alerts", True):
                lines = "\n".join(f"- {r['job'].title} at {r['job'].company_name} ({round(r['match'])}% match)" for r in high[:5])
                notifications.notify(db, user, "high_match", f"{len(high)} new high-match job{'s' if len(high) > 1 else ''} for you", f"New jobs that closely fit your profile:\n{lines}", "/candidate/recommendations")
                sent += 1
            elif fresh and prefs.get("new_recommendations", True):
                lines = "\n".join(f"- {r['job'].title} at {r['job'].company_name} ({round(r['match'])}% match)" for r in fresh[:5])
                notifications.notify(db, user, "new_recommendations", "New job recommendations", f"Jobs picked for you:\n{lines}", "/candidate/recommendations")
                sent += 1
            db.commit()
    return sent


def run_backup() -> Path | None:
    path = settings.database_url.replace("sqlite:///", "")
    if not Path(path).exists():
        return None
    target = Path(settings.backup_dir)
    target.mkdir(parents=True, exist_ok=True)
    destination = target / f"pathwise-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.db"
    import sqlite3

    source = sqlite3.connect(path)
    dest = sqlite3.connect(destination)
    with dest:
        source.backup(dest)
    dest.close()
    source.close()
    backups = sorted(target.glob("pathwise-*.db"))
    for old in backups[:-14]:
        old.unlink(missing_ok=True)
    return destination


def tick():
    with SessionLocal() as db:
        resume_service.process_pending(db)
    notifications.process_outbox()
    now = time.time()
    if now - _state["last_expiry"] > 900:
        _state["last_expiry"] = now
        with SessionLocal() as db:
            job_service.expire_stale_jobs(db)
        run_ingestion()
    if now - _state["last_alerts"] > 6 * 3600:
        _state["last_alerts"] = now
        run_job_alerts()
    if now - _state["last_backup"] > 24 * 3600:
        _state["last_backup"] = now
        run_backup()


def loop():
    logger.info("background worker started")
    while not _stop.is_set():
        try:
            tick()
        except Exception:
            logger.exception("worker tick failed")
        _stop.wait(settings.worker_interval_seconds)


def start() -> threading.Thread | None:
    if not settings.worker_enabled:
        return None
    _stop.clear()
    thread = threading.Thread(target=loop, name="pathwise-worker", daemon=True)
    thread.start()
    return thread


def stop():
    _stop.set()
