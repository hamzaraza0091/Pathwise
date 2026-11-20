from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_prefix="PATHWISE_", extra="ignore")

    app_name: str = "Pathwise"
    database_url: str = f"sqlite:///{BASE_DIR / 'pathwise.db'}"
    secret_key: str = "change-me-in-production-please-use-a-long-random-value"
    access_token_minutes: int = 60 * 24
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    storage_dir: Path = BASE_DIR / "storage"
    max_resume_bytes: int = 5 * 1024 * 1024
    rate_limit_per_minute: int = 120
    auth_rate_limit_per_minute: int = 10
    frontend_url: str = "http://localhost:5173"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    mail_from: str = "no-reply@pathwise.local"
    admin_email: str = ""
    admin_password: str = ""
    auto_create_tables: bool = False
    require_email_verification: bool = False
    email_backend: str = "console"
    email_max_attempts: int = 5
    embedding_backend: str = "auto"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    llm_extraction_enabled: bool = False
    anthropic_api_key: str = ""
    llm_model: str = "claude-haiku-5-5"
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    adzuna_country: str = "gb"
    worker_enabled: bool = True
    worker_interval_seconds: int = 30
    high_match_threshold: int = 80
    job_default_ttl_days: int = 45
    backup_dir: Path = BASE_DIR / "backups"
    http_user_agent: str = "PathwiseBot/1.0 (job aggregation via official APIs)"


settings = Settings()
