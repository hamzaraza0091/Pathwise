import hashlib
import re
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser

from app.constants import EDUCATION_LEVELS

BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section"}


class _Stripper(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.skip += 1
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.skip = max(0, self.skip - 1)
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(value: str | None) -> str:
    if not value:
        return ""
    stripper = _Stripper()
    try:
        stripper.feed(value)
        text = "".join(stripper.parts)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", value)
    text = unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return "\n".join(line.strip() for line in text.splitlines()).strip()


def clean_title(title: str) -> str:
    title = unescape(re.sub(r"\s+", " ", title or "")).strip()
    title = re.sub(r"^\W+|\W+$", "", title)
    title = re.sub(r"\s*[\(\[]\s*(remote|hybrid|onsite|on-site|m/f/d|f/m/d|m/w/d|w/m/d|all genders)\s*[\)\]]\s*$", "", title, flags=re.I)
    return title[:300]


def normalize_key(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+# ]", " ", (value or "").lower())).strip()


def dedupe_hash(title: str, company: str, location: str | None, remote: bool) -> str:
    loc = "remote" if remote else normalize_key((location or "").split(",")[0])
    return hashlib.sha1(f"{normalize_key(title)}|{normalize_key(company)}|{loc}".encode()).hexdigest()


def content_hash(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()


def map_employment_type(*values: str | None) -> str:
    text = " ".join(v for v in values if v).lower().replace("-", "_").replace(" ", "_")
    for needle, result in (("part_time", "part_time"), ("parttime", "part_time"), ("intern", "internship"), ("contract", "contract"), ("freelance", "freelance"), ("temporary", "temporary"), ("temp", "temporary"), ("full_time", "full_time"), ("fulltime", "full_time"), ("permanent", "full_time")):
        if needle in text:
            return result
    return "full_time"


def infer_level(title: str, description: str = "", raw: str | None = None) -> str | None:
    blob = f"{raw or ''} {title}".lower()
    table = (
        (r"\b(chief|vp|vice president|director|head of|executive)\b", "Executive"),
        (r"\b(lead|principal|staff|architect|manager)\b", "Lead"),
        (r"\b(senior|sr\.?)\b", "Senior"),
        (r"\b(mid|middle|intermediate|mid-level)\b", "Mid Level"),
        (r"\b(junior|jr\.?|associate)\b", "Junior"),
        (r"\b(intern|internship|trainee|entry|graduate|apprentice)\b", "Entry Level"),
    )
    for pattern, level in table:
        if re.search(pattern, blob):
            return level
    years = extract_min_years(description)
    if years is not None:
        if years < 1:
            return "Entry Level"
        if years < 3:
            return "Junior"
        if years < 5:
            return "Mid Level"
        if years < 8:
            return "Senior"
        return "Lead"
    return None


def extract_min_years(text: str) -> float | None:
    if not text:
        return None
    candidates = []
    for match in re.finditer(r"(\d{1,2})\s*(?:\+|-\s*\d{1,2}|to\s*\d{1,2})?\s*\+?\s*(?:years?|yrs?)(?:\s+of)?(?:\s+(?:relevant|professional|hands-on|commercial|working))?(?:\s+experience)?", text, re.I):
        window = text[max(0, match.start() - 60): match.end() + 60].lower()
        if "experience" in window:
            value = float(match.group(1))
            if 0 <= value <= 25:
                candidates.append(value)
    return min(candidates) if candidates else None


def extract_education_required(text: str) -> str | None:
    if not text:
        return None
    lower = text.lower()
    if re.search(r"\b(ph\.?d|doctorate)\b", lower) and re.search(r"(required|must|degree)", lower):
        return "phd"
    if re.search(r"\b(master'?s?|m\.?sc|mba)\b", lower) and re.search(r"(required|degree|must|in a related)", lower):
        return "master"
    if re.search(r"\b(bachelor'?s?|b\.?sc|undergraduate degree|bs/ms|university degree|college degree)\b", lower):
        return "bachelor"
    return None


def parse_salary(text: str | None, minimum=None, maximum=None, currency: str | None = None):
    def to_number(value):
        try:
            return float(value) if value not in (None, "", 0, "0") else None
        except (TypeError, ValueError):
            return None

    lo, hi = to_number(minimum), to_number(maximum)
    cur = currency
    if lo is None and hi is None and text:
        symbols = {"$": "USD", "£": "GBP", "€": "EUR"}
        for symbol, code in symbols.items():
            if symbol in text:
                cur = cur or code
        if not cur:
            found = re.search(r"\b(USD|EUR|GBP|CAD|AUD|PKR|INR)\b", text)
            cur = found.group(1) if found else None
        numbers = []
        for m in re.finditer(r"(\d[\d,\.]*)\s*([kK])?", text):
            raw = m.group(1).replace(",", "")
            try:
                n = float(raw)
            except ValueError:
                continue
            if m.group(2):
                n *= 1000
            if n >= 1000:
                numbers.append(n)
        if numbers:
            lo, hi = min(numbers), max(numbers)
    if lo and hi and lo > hi:
        lo, hi = hi, lo
    if lo is not None and lo < 100 or hi is not None and hi < 100:
        return None, None, cur
    return lo, hi, cur


CATEGORY_RULES = (
    ("Data & AI", r"data (scien|analy|engineer)|machine learning|\bml\b|\bai\b|artificial intelligence|nlp|analytics|bi developer"),
    ("DevOps & Infrastructure", r"devops|sre|site reliability|infrastructure|cloud engineer|platform engineer|sysadmin|system administrator"),
    ("Software Development", r"software|developer|engineer|programmer|backend|frontend|front-end|back-end|full.?stack|mobile|qa |web dev"),
    ("Design", r"design|ux|ui |creative|illustrat"),
    ("Product", r"product (manager|owner)|product management|scrum master|project manager"),
    ("Marketing", r"marketing|seo|growth|content strateg|social media|brand"),
    ("Sales", r"sales|account executive|business development|\bsdr\b|\bbdr\b"),
    ("Customer Support", r"support|customer success|customer service|help desk"),
    ("Finance", r"financ|account|bookkeep|auditor|controller"),
    ("Human Resources", r"recruit|talent|\bhr\b|human resources|people ops"),
    ("Writing & Content", r"writer|editor|copywrit|content"),
    ("Healthcare", r"nurse|medical|health|clinical|physician"),
    ("Education", r"teacher|tutor|instructor|lecturer|education"),
    ("Operations", r"operations|logistics|supply chain|administrat|office manager"),
)


def map_category(title: str, raw_category: str | None = None) -> str:
    blob = f"{title} {raw_category or ''}".lower()
    for name, pattern in CATEGORY_RULES:
        if re.search(pattern, blob):
            return name
    return "Other"


REMOTE_WORDS = re.compile(r"\b(remote|worldwide|anywhere|work from home|wfh|distributed)\b", re.I)


def infer_work_mode(location: str | None, title: str, description: str, remote_flag: bool | None) -> str:
    if remote_flag is True:
        return "remote"
    blob = f"{location or ''} {title}".lower()
    if "hybrid" in blob or re.search(r"\bhybrid\b", description[:1500].lower()):
        return "hybrid"
    if REMOTE_WORDS.search(blob):
        return "remote"
    if remote_flag is False:
        return "onsite"
    return "onsite"


def split_location(location: str | None) -> tuple[str | None, str | None]:
    if not location:
        return None, None
    parts = [p.strip() for p in re.split(r",|/|;", location) if p.strip()]
    parts = [p for p in parts if not REMOTE_WORDS.fullmatch(p) and p.lower() not in {"remote", "hybrid"}]
    if not parts:
        return None, None
    if len(parts) == 1:
        return None, parts[0]
    return parts[0], parts[-1]


def to_utc(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value > 1e12:
            value /= 1000
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    from email.utils import parsedate_to_datetime

    try:
        parsed = parsedate_to_datetime(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def education_rank(level: str | None) -> int:
    return EDUCATION_LEVELS.get(level or "none", 0)
