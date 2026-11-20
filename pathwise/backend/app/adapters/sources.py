import xml.etree.ElementTree as ET

import httpx

from app.adapters.base import Adapter, RawJob, SourceError
from app.core.config import settings


def _json(adapter: Adapter, response: httpx.Response):
    try:
        return response.json()
    except ValueError:
        raise SourceError(f"{adapter.name} returned an invalid response")


class RemotiveAdapter(Adapter):
    key = "remotive"
    name = "Remotive"
    base_url = "https://remotive.com"
    terms_url = "https://github.com/remotive-com/remote-jobs-api"
    min_refresh_minutes = 360
    default_refresh_minutes = 360

    def fetch(self, client):
        data = _json(self, self.get(client, "https://remotive.com/api/remote-jobs", params={"limit": self.config.get("limit", 100)}))
        jobs = []
        for item in data.get("jobs", []):
            jobs.append(RawJob(
                external_id=str(item.get("id")), title=item.get("title") or "", company=item.get("company_name") or "",
                description=item.get("description") or "", url=item.get("url"), apply_url=item.get("url"),
                location=item.get("candidate_required_location"), remote=True, employment_type=item.get("job_type"),
                category=item.get("category"), tags=item.get("tags") or [], salary_text=item.get("salary"), published_at=item.get("publication_date"),
            ))
        return jobs


class ArbeitnowAdapter(Adapter):
    key = "arbeitnow"
    name = "Arbeitnow"
    base_url = "https://www.arbeitnow.com"
    terms_url = "https://www.arbeitnow.com/blog/job-board-api"
    min_refresh_minutes = 60

    def fetch(self, client):
        data = _json(self, self.get(client, "https://www.arbeitnow.com/api/job-board-api"))
        jobs = []
        for item in data.get("data", []):
            jobs.append(RawJob(
                external_id=str(item.get("slug")), title=item.get("title") or "", company=item.get("company_name") or "",
                description=item.get("description") or "", url=item.get("url"), apply_url=item.get("url"), location=item.get("location"),
                remote=item.get("remote"), employment_type=" ".join(item.get("job_types") or []), tags=item.get("tags") or [], published_at=item.get("created_at"),
            ))
        return jobs


class JobicyAdapter(Adapter):
    key = "jobicy"
    name = "Jobicy"
    base_url = "https://jobicy.com"
    terms_url = "https://jobicy.com/jobs-rss-feed"
    min_refresh_minutes = 60

    def fetch(self, client):
        data = _json(self, self.get(client, "https://jobicy.com/api/v2/remote-jobs", params={"count": self.config.get("count", 50)}))
        jobs = []
        for item in data.get("jobs", []):
            job_type = item.get("jobType")
            jobs.append(RawJob(
                external_id=str(item.get("id")), title=item.get("jobTitle") or "", company=item.get("companyName") or "",
                description=item.get("jobDescription") or item.get("jobExcerpt") or "", url=item.get("url"), apply_url=item.get("url"),
                location=item.get("jobGeo"), remote=True, employment_type=" ".join(job_type) if isinstance(job_type, list) else job_type,
                category=" ".join(item.get("jobIndustry") or []) if isinstance(item.get("jobIndustry"), list) else item.get("jobIndustry"),
                level=item.get("jobLevel"), salary_min=item.get("salaryMin") or item.get("annualSalaryMin"), salary_max=item.get("salaryMax") or item.get("annualSalaryMax"),
                salary_currency=item.get("salaryCurrency"), published_at=item.get("pubDate"),
            ))
        return jobs


class RemoteOkAdapter(Adapter):
    key = "remoteok"
    name = "Remote OK"
    base_url = "https://remoteok.com"
    terms_url = "https://remoteok.com/api"
    min_refresh_minutes = 360
    default_refresh_minutes = 720

    def fetch(self, client):
        data = _json(self, self.get(client, "https://remoteok.com/api"))
        jobs = []
        for item in data if isinstance(data, list) else []:
            if not isinstance(item, dict) or not item.get("position"):
                continue
            jobs.append(RawJob(
                external_id=str(item.get("id") or item.get("slug")), title=item.get("position") or "", company=item.get("company") or "",
                description=item.get("description") or "", url=item.get("url"), apply_url=item.get("apply_url") or item.get("url"),
                location=item.get("location"), remote=True, tags=item.get("tags") or [], salary_min=item.get("salary_min"),
                salary_max=item.get("salary_max"), salary_currency="USD" if item.get("salary_min") else None, published_at=item.get("date") or item.get("epoch"),
            ))
        return jobs


class AdzunaAdapter(Adapter):
    key = "adzuna"
    name = "Adzuna"
    base_url = "https://www.adzuna.com"
    terms_url = "https://developer.adzuna.com/docs/terms_of_service"
    min_refresh_minutes = 120
    requires_credentials = True

    def configured(self):
        return bool((self.config.get("app_id") or settings.adzuna_app_id) and (self.config.get("app_key") or settings.adzuna_app_key))

    def fetch(self, client):
        if not self.configured():
            raise SourceError("Adzuna API credentials are not configured")
        country = self.config.get("country") or settings.adzuna_country
        params = {"app_id": self.config.get("app_id") or settings.adzuna_app_id, "app_key": self.config.get("app_key") or settings.adzuna_app_key, "results_per_page": 50, "content-type": "application/json"}
        if self.config.get("what"):
            params["what"] = self.config["what"]
        jobs = []
        for page in range(1, int(self.config.get("pages", 2)) + 1):
            data = _json(self, self.get(client, f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}", params=params))
            for item in data.get("results", []):
                jobs.append(RawJob(
                    external_id=str(item.get("id")), title=item.get("title") or "", company=(item.get("company") or {}).get("display_name") or "",
                    description=item.get("description") or "", url=item.get("redirect_url"), apply_url=item.get("redirect_url"),
                    location=(item.get("location") or {}).get("display_name"), employment_type=item.get("contract_time") or item.get("contract_type"),
                    category=(item.get("category") or {}).get("label"), salary_min=item.get("salary_min"), salary_max=item.get("salary_max"),
                    salary_currency=self.config.get("currency"), published_at=item.get("created"),
                ))
        return jobs


class RssAdapter(Adapter):
    key = "rss"
    name = "RSS Feed"
    min_refresh_minutes = 60

    def fetch(self, client):
        url = self.config.get("url")
        if not url:
            raise SourceError("RSS source has no feed URL configured")
        response = self.get(client, url, headers={"Accept": "application/rss+xml, application/xml, text/xml"})
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError:
            raise SourceError("The feed is not valid XML")
        ns = {"content": "http://purl.org/rss/1.0/modules/content/"}
        jobs = []
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            guid = (item.findtext("guid") or link or title).strip()
            company = (item.findtext("company") or item.findtext("{*}company") or self.config.get("default_company") or "").strip()
            if not company and " at " in title:
                title, company = title.rsplit(" at ", 1)
            description = item.findtext("content:encoded", namespaces=ns) or item.findtext("description") or ""
            jobs.append(RawJob(external_id=guid, title=title, company=company.strip(), description=description, url=link, apply_url=link,
                               location=item.findtext("location") or item.findtext("{*}location"), published_at=item.findtext("pubDate"), category=item.findtext("category")))
        return jobs


ADAPTERS = {cls.key: cls for cls in (RemotiveAdapter, ArbeitnowAdapter, JobicyAdapter, RemoteOkAdapter, AdzunaAdapter, RssAdapter)}
