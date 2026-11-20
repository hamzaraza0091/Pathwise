import re
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Skill

TECHNICAL = """
Python|py
JavaScript|js|ecmascript
TypeScript|ts
Java
C++|cpp
C#|csharp|c sharp
Go|golang
Rust
Ruby
PHP
Swift
Kotlin
Scala
R
MATLAB
SQL
NoSQL
HTML|html5
CSS|css3
React|reactjs|react.js
Next.js|nextjs
Vue|vue.js|vuejs
Angular|angularjs
Svelte
Node.js|nodejs|node
Express|express.js|expressjs
FastAPI
Flask
Django
Spring Boot|springboot|spring
.NET|dotnet|asp.net
Laravel
Ruby on Rails|rails
GraphQL
REST API|rest apis|restful|rest
gRPC
Tailwind CSS|tailwind
Redux
PostgreSQL|postgres
MySQL
SQLite
MongoDB|mongo
Redis
Elasticsearch
Cassandra
DynamoDB
Snowflake
BigQuery
Kafka|apache kafka
RabbitMQ
Spark|apache spark|pyspark
Hadoop
Airflow|apache airflow
dbt
ETL
Docker
Kubernetes|k8s
Terraform
Ansible
Jenkins
GitHub Actions
GitLab CI
CI/CD|cicd|ci cd
AWS|amazon web services
Azure
GCP|google cloud|google cloud platform
Linux
Bash|shell scripting
Git
Nginx
Prometheus
Grafana
Machine Learning|ml
Deep Learning
Natural Language Processing|nlp
Computer Vision
Data Science
Data Analysis
Data Engineering
Data Visualization
Statistics
Pandas
NumPy
SciPy
scikit-learn|sklearn
TensorFlow
PyTorch
Keras
Hugging Face|huggingface
Transformers
spaCy
OpenCV
LangChain
LlamaIndex
RAG|retrieval augmented generation|retrieval-augmented generation
LLM|llms|large language models
Prompt Engineering
Generative AI|genai
Vector Databases|vector database
MLOps
Reinforcement Learning
Tableau
Power BI|powerbi
Excel|microsoft excel
Looker
Jupyter
Unity
Unreal Engine
Android
iOS
React Native
Flutter
Figma
Adobe XD
Photoshop
Illustrator
UI/UX|ux design|ui design
Selenium
Cypress
Jest
pytest
Unit Testing
Test Automation
Microservices
System Design
Distributed Systems
OOP|object-oriented programming|object oriented programming
Data Structures
Algorithms
Agile
Scrum
Jira
Kanban
SEO
Google Analytics
Salesforce
HubSpot
SAP
QuickBooks
Accounting
Financial Modeling
Cybersecurity|information security
Penetration Testing
OAuth
WebSockets
Celery
SQLAlchemy
Alembic
Pydantic
Postman
Swagger|openapi
Blockchain
Solidity
Embedded Systems
IoT
Arduino
Raspberry Pi
"""
SOFT = """
Communication|communication skills
Leadership
Teamwork|team player|collaboration
Problem Solving|problem-solving
Critical Thinking
Time Management
Adaptability
Creativity
Project Management
Mentoring
Presentation Skills
Negotiation
Attention to Detail
Analytical Thinking|analytical skills
"""
RELATED = [
    {"python", "django", "flask", "fastapi"},
    {"javascript", "typescript", "node.js"},
    {"react", "vue", "angular", "svelte", "next.js"},
    {"postgresql", "mysql", "sqlite", "sql"},
    {"aws", "azure", "gcp"},
    {"docker", "kubernetes"},
    {"tensorflow", "pytorch", "keras"},
    {"machine learning", "deep learning", "data science"},
    {"langchain", "llamaindex", "rag", "llm"},
    {"tableau", "power bi", "looker"},
    {"jenkins", "github actions", "gitlab ci", "ci/cd"},
    {"java", "kotlin", "spring boot"},
    {"c#", ".net"},
    {"mongodb", "nosql", "dynamodb", "cassandra"},
    {"pytest", "jest", "cypress", "selenium", "unit testing", "test automation"},
]
AMBIGUOUS = {"go", "r", "c", "rest", "node", "spring", "shell scripting", "transformers", "express", "swift", "rails", "excel", "ml", "py", "ts", "js", "unity", "rust"}
CASE_SENSITIVE = {"Go", "R", "C", "Swift", "Rust", "Unity", "Express", "Transformers"}

_version = {"n": 0}


def bump_version():
    _version["n"] += 1


def parse_block(block: str, kind: str):
    for line in block.strip().splitlines():
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if parts:
            yield parts[0], kind, parts[1:]


def seed_skills(db: Session):
    existing = {s.name.lower() for s in db.scalars(select(Skill))}
    for name, kind, aliases in [*parse_block(TECHNICAL, "technical"), *parse_block(SOFT, "soft")]:
        if name.lower() not in existing:
            db.add(Skill(name=name, kind=kind, aliases=aliases))
    db.commit()


def canonical(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


class SkillIndex:
    def __init__(self, rows):
        self.by_name: dict[str, tuple[str, str]] = {}
        self.patterns: list[tuple[re.Pattern, str, str]] = []
        for name, kind, aliases in rows:
            canon = canonical(name)
            self.by_name[canon] = (name, kind)
            for phrase in {name, *aliases}:
                if canonical(phrase) in AMBIGUOUS and phrase not in CASE_SENSITIVE and canonical(phrase) != canon:
                    continue
                flags = 0 if (phrase in CASE_SENSITIVE or canonical(phrase) in {"go", "r", "c"} and phrase == name) else re.IGNORECASE
                if canonical(phrase) in {"go", "r", "c"}:
                    flags = 0
                escaped = re.escape(phrase).replace(r"\ ", r"[\s\-]+")
                pattern = re.compile(rf"(?<![A-Za-z0-9+#]){escaped}(?![A-Za-z0-9]|\+\+|#)" if not phrase.endswith(("+", "#")) else rf"(?<![A-Za-z0-9+#]){escaped}(?![A-Za-z0-9])", flags)
                self.patterns.append((pattern, name, kind))

    def find(self, text: str, kinds=("technical", "soft")):
        found: dict[str, dict] = {}
        lines = text.split("\n")
        offsets, pos = [], 0
        for line in lines:
            offsets.append(pos)
            pos += len(line) + 1
        for pattern, name, kind in self.patterns:
            if kind not in kinds:
                continue
            for match in pattern.finditer(text):
                if canonical(name) in {"r", "c"}:
                    after = text[match.end(): match.end() + 2]
                    before = text[max(0, match.start() - 2): match.start()]
                    if after.strip().startswith(("&", "/")) or before.strip().endswith(("&", "/")):
                        continue
                canon = canonical(name)
                entry = found.setdefault(canon, {"skill": name, "kind": kind, "count": 0, "evidence": None, "lines": []})
                entry["count"] += 1
                idx = max(i for i, off in enumerate(offsets) if off <= match.start())
                entry["lines"].append(idx)
                if entry["evidence"] is None:
                    entry["evidence"] = lines[idx].strip()[:240]
        return found


_index_cache: dict[tuple, SkillIndex] = {}


def get_index(db: Session) -> SkillIndex:
    row = db.execute(select(func.count(Skill.id), func.coalesce(func.max(Skill.id), 0), func.coalesce(func.sum(Skill.is_active), 0))).one()
    key = (*row, _version["n"])
    if key not in _index_cache:
        _index_cache.clear()
        rows = db.execute(select(Skill.name, Skill.kind, Skill.aliases).where(Skill.is_active.is_(True))).all()
        _index_cache[key] = SkillIndex([(n, k, a or []) for n, k, a in rows])
    return _index_cache[key]


PREFERRED_HINT = re.compile(r"nice to have|nice-to-have|preferred|bonus|a plus|is a plus|desirable|good to have|optional|advantage|ideally|not required", re.I)
REQUIRED_HINT = re.compile(r"requirements?|qualifications?|must have|must-have|required|what you.?ll need|you have|you bring|skills|experience with|responsibilities", re.I)
HEADING = re.compile(r"^[\W_]*([A-Za-z][A-Za-z /&'’\-]{2,50})[:\W_]*$")


def classify_job_skills(db: Session, text: str, tags: list[str] | None = None) -> tuple[list[str], list[str]]:
    index = get_index(db)
    found = index.find(text, kinds=("technical",))
    section = "required"
    line_section: dict[int, str] = {}
    for i, line in enumerate(text.split("\n")):
        stripped = line.strip()
        if stripped and len(stripped) < 60 and HEADING.match(stripped):
            if PREFERRED_HINT.search(stripped):
                section = "preferred"
            elif REQUIRED_HINT.search(stripped) or re.search(r"about|role|overview|who we are|benefits|company", stripped, re.I):
                section = "required"
        line_section[i] = "preferred" if PREFERRED_HINT.search(stripped) else section
    required, preferred = [], []
    for canon, entry in found.items():
        kinds = {line_section.get(i, "required") for i in entry["lines"]}
        (required if "required" in kinds else preferred).append(entry["skill"])
    for tag in tags or []:
        canon = canonical(tag)
        if canon in index.by_name and index.by_name[canon][1] == "technical":
            name = index.by_name[canon][0]
            if name not in required and name not in preferred:
                required.append(name)
    return sorted(required), sorted(preferred)


def related_to(a: str, b: str) -> bool:
    a, b = canonical(a), canonical(b)
    return a != b and any(a in group and b in group for group in RELATED)
