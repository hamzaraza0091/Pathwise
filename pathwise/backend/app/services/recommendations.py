import re
import uuid
from datetime import datetime, timezone

import numpy as np
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models import Application, CandidateProfile, Job, JobView, RecommendationHistory, SavedJob
from app.models.users import utcnow
from app.services import embeddings, matching
from app.services.jobs import fts_ready
from app.services.normalize import aware
from app.services.search import TS


def interaction_profile(db: Session, profile: CandidateProfile) -> dict:
    ids = [r[0] for r in db.execute(select(SavedJob.job_id).where(SavedJob.candidate_id == profile.id))]
    ids += [r[0] for r in db.execute(select(JobView.job_id).where(JobView.user_id == profile.user_id).order_by(JobView.id.desc()).limit(30))]
    ids += [r[0] for r in db.execute(select(Application.job_id).where(Application.candidate_id == profile.id))]
    categories, skills = {}, {}
    if ids:
        for job in db.scalars(select(Job).options(selectinload(Job.skills)).where(Job.id.in_(set(ids)))):
            if job.category_id:
                categories[job.category_id] = categories.get(job.category_id, 0) + 1
            for s in job.skills:
                skills[s.skill.lower()] = skills.get(s.skill.lower(), 0) + 1
    return {"categories": categories, "skills": skills, "seen": set(ids)}


def interaction_bonus(job: Job, interactions: dict) -> float:
    if not interactions["categories"] and not interactions["skills"]:
        return 0.0
    bonus = 0.0
    if job.category_id in interactions["categories"]:
        total = sum(interactions["categories"].values())
        bonus += 3.0 * interactions["categories"][job.category_id] / total
    job_skills = {s.skill.lower() for s in job.skills}
    if job_skills and interactions["skills"]:
        top = sorted(interactions["skills"], key=interactions["skills"].get, reverse=True)[:15]
        bonus += 2.0 * len(job_skills & set(top)) / len(job_skills)
    return round(bonus, 2)


def retrieval_query(snapshot: matching.CandidateSnapshot) -> str | None:
    terms = []
    for skill in list(snapshot.skills.values())[:14]:
        terms.append(f'"{skill.lower()}"')
    for title in (snapshot.desired_titles + snapshot.titles)[:4]:
        words = [w for w in re.findall(r"[a-z0-9+#]+", title.lower()) if len(w) > 2 and w not in matching.STOP]
        if words:
            terms.append('"' + " ".join(words) + '"')
    return " OR ".join(dict.fromkeys(terms)) or None


def retrieve(db: Session, profile: CandidateProfile, snapshot: matching.CandidateSnapshot, interactions: dict, limit: int = 300) -> list[int]:
    now = utcnow().strftime(TS)
    base = "j.status = 'active' AND (j.expires_at IS NULL OR j.expires_at > :now)"
    ids: list[int] = []
    expr = retrieval_query(snapshot)
    if expr and fts_ready(db):
        try:
            rows = db.execute(text(f"SELECT j.id FROM jobs_fts JOIN jobs j ON j.id = jobs_fts.rowid WHERE jobs_fts MATCH :q AND {base} ORDER BY bm25(jobs_fts, 10.0, 4.0, 1.0, 6.0) LIMIT :lim"), {"q": expr, "now": now, "lim": limit}).all()
            ids.extend(r[0] for r in rows)
        except Exception:
            pass
    if embeddings.has_dense() and snapshot.text.strip():
        query_vec = embeddings.embed_dense([snapshot.text])
        if query_vec is not None:
            rows = db.execute(text(f"SELECT j.id, j.embedding FROM jobs j WHERE j.embedding IS NOT NULL AND j.embedding_model = :m AND {base}"), {"m": settings.embedding_model, "now": now}).all()
            if rows:
                matrix = np.stack([embeddings.from_blob(r[1]) for r in rows])
                top = np.argsort(-(matrix @ query_vec[0]))[:100]
                ids.extend(rows[i][0] for i in top)
    if len(set(ids)) < 60:
        rows = db.execute(text(f"SELECT j.id FROM jobs j WHERE {base} ORDER BY j.published_at DESC LIMIT 150"), {"now": now}).all()
        ids.extend(r[0] for r in rows)
    applied = set(r[0] for r in db.execute(select(Application.job_id).where(Application.candidate_id == profile.id)))
    return [i for i in dict.fromkeys(ids) if i not in applied][:limit * 2]


def rank(db: Session, profile: CandidateProfile, limit: int = 300) -> list[dict]:
    snapshot = matching.build_candidate_snapshot(db, profile)
    if not snapshot.has_profile_data:
        return []
    interactions = interaction_profile(db, profile)
    model = matching.active_model(db)
    signature = snapshot.signature()
    ids = retrieve(db, profile, snapshot, interactions, limit)
    results = []
    if not ids:
        return results
    jobs = db.scalars(select(Job).options(selectinload(Job.skills), selectinload(Job.source), selectinload(Job.category), selectinload(Job.company)).where(Job.id.in_(ids))).all()
    seen_hashes = set()
    order = {i: n for n, i in enumerate(ids)}
    for job in sorted(jobs, key=lambda j: order[j.id]):
        if job.dedupe_hash in seen_hashes:
            continue
        seen_hashes.add(job.dedupe_hash)
        result = matching.get_or_compute(db, profile, job, snapshot, model, signature)
        results.append({"job": job, "match": result["score"], "rank_score": min(100.0, result["score"] + interaction_bonus(job, interactions)), "explanation": result})
    db.commit()
    results.sort(key=lambda r: (-r["rank_score"], -aware(r["job"].published_at).timestamp()))
    return results


def persist_batch(db: Session, profile: CandidateProfile, ranked: list[dict], top: int = 50) -> str:
    batch = uuid.uuid4().hex[:12]
    previous = {r[0] for r in db.execute(select(RecommendationHistory.job_id).where(RecommendationHistory.candidate_id == profile.id))}
    for item in ranked[:top]:
        db.add(RecommendationHistory(candidate_id=profile.id, job_id=item["job"].id, score=item["match"], notified=item["job"].id in previous))
    db.commit()
    return batch


def apply_filters(items: list[dict], min_score: float | None, location: str | None, employment_type: str | None, experience_level: str | None, work_mode: str | None) -> list[dict]:
    out = items
    if min_score is not None:
        out = [i for i in out if i["match"] >= min_score]
    if location:
        needle = location.lower()
        out = [i for i in out if needle in (i["job"].location or "").lower()]
    if employment_type:
        out = [i for i in out if i["job"].employment_type == employment_type]
    if experience_level:
        out = [i for i in out if i["job"].experience_level == experience_level]
    if work_mode:
        out = [i for i in out if i["job"].work_mode == work_mode]
    return out
