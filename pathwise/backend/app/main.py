import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.config import settings
from app.core.database import Base, SessionLocal, engine, ensure_fts
from app.core.ratelimit import RateLimitMiddleware
from app.core.security import hash_password
from app.models import JobCategory, JobSource, MatchingModelVersion, User
from app.routers import admin, auth, candidate_ops, hiring, jobs, notifications, profiles
from app.services import aggregation, skills as skills_service, worker
from app.constants import DEFAULT_CATEGORIES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("pathwise")

DEFAULT_WEIGHTS = {"skills": 0.45, "experience": 0.20, "education": 0.10, "location": 0.10, "semantic": 0.10, "preferences": 0.05}


def seed():
    with SessionLocal() as db:
        if not db.scalar(select(JobSource).where(JobSource.key == "pathwise")):
            db.add(JobSource(key="pathwise", name="Pathwise", is_native=True, refresh_minutes=0))
        if not db.scalar(select(MatchingModelVersion).where(MatchingModelVersion.version == "v1")):
            db.add(MatchingModelVersion(version="v1", weights=DEFAULT_WEIGHTS, is_active=True))
        if settings.admin_email and settings.admin_password:
            if not db.scalar(select(User).where(User.email == settings.admin_email.lower())):
                db.add(
                    User(
                        email=settings.admin_email.lower(),
                        password_hash=hash_password(settings.admin_password),
                        full_name="Administrator",
                        role="admin",
                        email_verified=True,
                    )
                )
        db.commit()
        existing = {c.name for c in db.scalars(select(JobCategory))}
        for name in DEFAULT_CATEGORIES:
            if name not in existing:
                db.add(JobCategory(name=name, slug=re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")))
        db.commit()
        aggregation.seed_sources(db)
        skills_service.seed_skills(db)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_create_tables:
        Base.metadata.create_all(engine)
    with engine.begin() as connection:
        ensure_fts(connection)
    seed()
    worker.start()
    yield
    worker.stop()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    errors = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
    return JSONResponse({"detail": "Please check the highlighted fields", "errors": errors}, status_code=422)


@app.exception_handler(IntegrityError)
async def integrity_handler(request: Request, exc: IntegrityError):
    logger.warning("integrity error: %s", exc.orig)
    return JSONResponse({"detail": "This record conflicts with existing data"}, status_code=409)


@app.exception_handler(OperationalError)
async def operational_handler(request: Request, exc: OperationalError):
    logger.error("database error: %s", exc.orig)
    return JSONResponse({"detail": "The service is temporarily busy. Please retry."}, status_code=503)


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    logger.exception("unhandled error")
    return JSONResponse({"detail": "Something went wrong on our side"}, status_code=500)


app.include_router(auth.router)
app.include_router(profiles.candidates)
app.include_router(profiles.employers)
app.include_router(profiles.recruiters)
app.include_router(jobs.router)
app.include_router(jobs.companies)
app.include_router(candidate_ops.router)
app.include_router(hiring.router)
app.include_router(notifications.router)
app.include_router(admin.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
