import re
from datetime import timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from app.models import Job, SearchHistory, Skill
from app.models.users import utcnow
from app.services.jobs import fts_ready

TS = "%Y-%m-%d %H:%M:%S.%f"


def fts_expression(query: str, mode: str = "and") -> str | None:
    tokens = re.findall(r"[\w+#.]+", query.lower())
    tokens = [t.strip(".") for t in tokens if t.strip(".")]
    if not tokens:
        return None
    parts = [f'"{t}"' for t in tokens[:-1]] + [f'"{tokens[-1]}"*']
    return (" AND " if mode == "and" else " OR ").join(parts)


def build_filters(f: dict) -> tuple[str, dict]:
    clauses = ["j.status = 'active'", "(j.expires_at IS NULL OR j.expires_at > :now)"]
    params: dict = {"now": utcnow().strftime(TS)}
    clauses.append(
        "NOT EXISTS (SELECT 1 FROM jobs d JOIN job_sources ds ON ds.id = d.source_id JOIN job_sources js ON js.id = j.source_id "
        "WHERE d.dedupe_hash = j.dedupe_hash AND d.status = 'active' AND d.id <> j.id AND "
        "(ds.is_native > js.is_native OR (ds.is_native = js.is_native AND d.id < j.id)))"
    )
    if f.get("title"):
        clauses.append("lower(j.title) LIKE :title")
        params["title"] = f"%{f['title'].lower()}%"
    if f.get("company"):
        clauses.append("lower(j.company_name) LIKE :company")
        params["company"] = f"%{f['company'].lower()}%"
    if f.get("company_id"):
        clauses.append("j.company_id = :company_id")
        params["company_id"] = f["company_id"]
    if f.get("location"):
        clauses.append("(lower(j.location) LIKE :loc OR EXISTS (SELECT 1 FROM job_locations l WHERE l.job_id = j.id AND (lower(l.city) LIKE :loc OR lower(l.country) LIKE :loc)))")
        params["loc"] = f"%{f['location'].lower()}%"
    for key, column in (("work_mode", "j.work_mode"), ("employment_type", "j.employment_type"), ("experience_level", "j.experience_level")):
        values = f.get(key)
        if values:
            names = []
            for i, value in enumerate(values):
                params[f"{key}{i}"] = value
                names.append(f":{key}{i}")
            clauses.append(f"{column} IN ({', '.join(names)})")
    if f.get("category"):
        clauses.append("j.category_id IN (SELECT id FROM job_categories WHERE slug = :category OR lower(name) = lower(:category))")
        params["category"] = f["category"]
    if f.get("source"):
        clauses.append("j.source_id IN (SELECT id FROM job_sources WHERE key = :source)")
        params["source"] = f["source"]
    if f.get("salary_min") is not None:
        clauses.append("COALESCE(j.salary_max, j.salary_min) >= :smin")
        params["smin"] = f["salary_min"]
    if f.get("salary_max") is not None:
        clauses.append("COALESCE(j.salary_min, j.salary_max) <= :smax")
        params["smax"] = f["salary_max"]
    if f.get("posted_within_days"):
        clauses.append("j.published_at >= :since")
        params["since"] = (utcnow() - timedelta(days=f["posted_within_days"])).strftime(TS)
    for i, skill in enumerate(f.get("skills") or []):
        clauses.append(f"EXISTS (SELECT 1 FROM job_skills s WHERE s.job_id = j.id AND lower(s.skill) = :sk{i})")
        params[f"sk{i}"] = skill.lower()
    if f.get("native_only"):
        clauses.append("j.source_id IN (SELECT id FROM job_sources WHERE is_native = 1)")
    return " AND ".join(clauses), params


ORDERS = {
    "date": "j.published_at DESC, j.id DESC",
    "salary": "COALESCE(j.salary_max, j.salary_min) IS NULL, COALESCE(j.salary_max, j.salary_min) DESC, j.published_at DESC",
}


def run_search(db: Session, filters: dict, sort: str, limit: int, offset: int):
    where, params = build_filters(filters)
    q = (filters.get("q") or "").strip()
    use_fts = bool(q) and fts_ready(db)
    rows, total, highlights = [], 0, {}
    if use_fts:
        for mode in ("and", "or"):
            expr = fts_expression(q, mode)
            if expr is None:
                use_fts = False
                break
            p = params | {"fts": expr, "limit": limit, "offset": offset}
            total = db.execute(text(f"SELECT COUNT(*) FROM jobs_fts JOIN jobs j ON j.id = jobs_fts.rowid WHERE jobs_fts MATCH :fts AND {where}"), p).scalar_one()
            if total or mode == "or" or len(expr.split(" AND ")) == 1:
                order = "rank" if sort in ("relevance", "match") else ORDERS.get(sort, ORDERS["date"])
                order = order if order != "rank" else "bm25(jobs_fts, 10.0, 4.0, 1.0, 6.0)"
                rows = db.execute(text(
                    f"SELECT j.id, highlight(jobs_fts, 0, '<mark>', '</mark>') AS h_title, highlight(jobs_fts, 1, '<mark>', '</mark>') AS h_company, "
                    f"snippet(jobs_fts, 2, '<mark>', '</mark>', '…', 28) AS snippet FROM jobs_fts JOIN jobs j ON j.id = jobs_fts.rowid "
                    f"WHERE jobs_fts MATCH :fts AND {where} ORDER BY {order} LIMIT :limit OFFSET :offset"), p).all()
                break
        highlights = {r.id: {"title": r.h_title, "company": r.h_company, "snippet": r.snippet} for r in rows}
        ids = [r.id for r in rows]
    if not use_fts:
        p = params | {"limit": limit, "offset": offset}
        if q:
            p["like"] = f"%{q.lower()}%"
            where_q = f"{where} AND (lower(j.title) LIKE :like OR lower(j.company_name) LIKE :like OR lower(j.description) LIKE :like)"
        else:
            where_q = where
        total = db.execute(text(f"SELECT COUNT(*) FROM jobs j WHERE {where_q}"), p).scalar_one()
        order = ORDERS.get(sort, ORDERS["date"])
        ids = [r[0] for r in db.execute(text(f"SELECT j.id FROM jobs j WHERE {where_q} ORDER BY {order} LIMIT :limit OFFSET :offset"), p).all()]
    jobs = {}
    if ids:
        for job in db.scalars(select(Job).options(selectinload(Job.skills), selectinload(Job.source), selectinload(Job.category), selectinload(Job.company)).where(Job.id.in_(ids))):
            jobs[job.id] = job
    return [jobs[i] for i in ids if i in jobs], total, highlights


def candidate_pool_ids(db: Session, filters: dict, sort: str, cap: int = 300) -> list[int]:
    jobs, _, _ = run_search(db, filters, "relevance" if filters.get("q") else "date", cap, 0)
    return [j.id for j in jobs]


def suggestions(db: Session, q: str, limit: int = 8) -> list[dict]:
    q = q.strip().lower()
    if len(q) < 2:
        return []
    like = f"{q}%"
    contains = f"%{q}%"
    out: list[dict] = []
    seen = set()

    def add(kind, value):
        key = (kind, value.lower())
        if key not in seen and len(out) < limit:
            seen.add(key)
            out.append({"type": kind, "value": value})

    for (title,) in db.execute(text("SELECT title FROM jobs WHERE status='active' AND lower(title) LIKE :p GROUP BY lower(title) ORDER BY COUNT(*) DESC LIMIT 5"), {"p": contains}):
        add("title", title)
    for (name,) in db.execute(text("SELECT company_name FROM jobs WHERE status='active' AND lower(company_name) LIKE :p GROUP BY lower(company_name) ORDER BY COUNT(*) DESC LIMIT 3"), {"p": like}):
        add("company", name)
    for skill in db.scalars(select(Skill.name).where(Skill.is_active.is_(True), Skill.kind == "technical").where(Skill.name.ilike(like)).limit(4)):
        add("skill", skill)
    return out


def record_search(db: Session, user_id: int, q: str | None, filters: dict, total: int):
    clean = {k: v for k, v in filters.items() if v not in (None, "", [], False) and k != "q"}
    if not q and not clean:
        return
    last = db.scalar(select(SearchHistory).where(SearchHistory.user_id == user_id).order_by(SearchHistory.id.desc()).limit(1))
    if last and last.query == (q or "") and last.filters == clean:
        return
    db.add(SearchHistory(user_id=user_id, query=(q or "")[:250], filters=clean, result_count=total))
