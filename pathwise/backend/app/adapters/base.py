import logging
import time
from dataclasses import dataclass, field
from datetime import datetime

import httpx

from app.core.config import settings

logger = logging.getLogger("pathwise.adapters")


class SourceError(Exception):
    pass


class RateLimited(SourceError):
    pass


@dataclass
class RawJob:
    external_id: str
    title: str
    company: str
    description: str
    url: str | None = None
    apply_url: str | None = None
    location: str | None = None
    remote: bool | None = None
    employment_type: str | None = None
    category: str | None = None
    level: str | None = None
    tags: list[str] = field(default_factory=list)
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_text: str | None = None
    published_at: datetime | int | float | str | None = None
    expires_at: datetime | None = None


class Adapter:
    key = ""
    name = ""
    base_url = ""
    terms_url = ""
    min_refresh_minutes = 60
    default_refresh_minutes = 360
    requires_credentials = False

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def configured(self) -> bool:
        return True

    def get(self, client: httpx.Client, url: str, **kwargs) -> httpx.Response:
        last = None
        for attempt in range(3):
            try:
                response = client.get(url, headers={"User-Agent": settings.http_user_agent, "Accept": "application/json"} | kwargs.pop("headers", {}), timeout=25, **kwargs)
            except httpx.HTTPError as error:
                last = SourceError(f"Network error contacting {self.name}: {error}")
                time.sleep(0.5 * (attempt + 1))
                continue
            if response.status_code == 429:
                raise RateLimited(f"{self.name} rate limit reached; will retry later")
            if response.status_code >= 500:
                last = SourceError(f"{self.name} returned HTTP {response.status_code}")
                time.sleep(0.5 * (attempt + 1))
                continue
            if response.status_code >= 400:
                raise SourceError(f"{self.name} returned HTTP {response.status_code}")
            return response
        raise last or SourceError(f"{self.name} unavailable")

    def fetch(self, client: httpx.Client) -> list[RawJob]:
        raise NotImplementedError
