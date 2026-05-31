from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

LINKEDIN_GUEST_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
LINKEDIN_PAST_MONTH = "r2592000"
LINKEDIN_PAGES = 4
REQUEST_DELAY_S = 1.5
JOB_RETENTION_DAYS = 7
RTDB_URL = os.getenv(
    "FIREBASE_RTDB_URL",
    "https://moran-cce72-default-rtdb.europe-west1.firebasedatabase.app",
).rstrip("/")
RTDB_SCOPES = [
    "https://www.googleapis.com/auth/firebase.database",
    "https://www.googleapis.com/auth/userinfo.email",
]

LINKEDIN_KEYWORDS = [
    "R&D Engineer",
    "Medical Device Engineer",
    "Mechanical Engineer",
    "Lab Technician",
    "Process Engineer",
    "Integration Engineer",
    "NPI Engineer",
    "Bioreactor Engineer",
    "Cell Culture Engineer",
    "Mechanical Design Engineer",
    "מהנדס מכשור רפואי",
    "מהנדס מכונות",
]
GREENHOUSE_COMPANIES = [
    "similarweb", "taboola", "monday", "wix", "fiverr", "riskified",
    "appsflyer", "lemonade", "redislabs", "jfrog", "medtronic",
    "insightec", "nanox", "evogene", "pluri",
]
TARGET_ROLES = [
    "Junior R&D Engineer", "R&D Engineer", "Lab Technician", "Mechanical Engineer",
    "Medical Engineer", "Process Engineer", "Integration Engineer", "NPI Engineer",
    "מהנדס", "מהנדסת",
]
KEYWORDS = [
    "solidworks", "mechanical design", "cad", "3d printing", "matlab", "python",
    "mechanical engineer", "r&d", "npi", "integration", "medical device",
    "medical devices", "medical engineer", "medical engineering", "מכשור רפואי",
    "מהנדס", "מהנדסת", "bioreactor", "bioreactors", "cell culture",
    "cultivated", "tissue culture", "bioprocess", "biotech", "foodtech",
    "food tech", "lab technician", "process engineer", "validation", "mfcs",
    "dot system", "dot systems", "flexcell", "trubio", "cellaca", "cedex",
    "bioanalyzer",
]
LOCATIONS = [
    "rehovot", "רחובות", "tel aviv", "תל אביב", "jerusalem", "ירושלים",
    "haifa", "חיפה", "beer sheba", "be'er sheva", "באר שבע", "israel", "ישראל",
]
NEGATIVE_TERMS = [
    "senior", "lead", "manager", "director", "head of", "vp ", "principal",
    "staff engineer", "team lead", "student", "intern", "internship", "מנהל",
    "מנהלת", "סטודנט", "סטודנטית", "מתמחה",
]
MED_ENG_FIELDS = [
    "biomedical engineering", "bio-medical engineering", "bio medical engineering",
    "medical engineering", "הנדסה רפואית", "הנדסה ביו-רפואית", "הנדסה ביורפואית",
]
DEGREE_WORDS = ["b.sc", "bsc", "b.s.", "b.eng", "beng", "bachelor", "degree", "תואר", "בוגר", "בוגרת"]
DEAD_MARKERS = [
    "no longer available", "no longer accepting", "no longer open", "position has been filled",
    "position has been closed", "job is closed", "this job is no longer", "posting is not available",
    "page not found", "404 not found", "job not found", "this position is closed",
    "applications are no longer", "המשרה אינה", "המשרה הוסרה", "משרה לא נמצאה", "המשרה נסגרה",
]
ALIVE = "alive"
DEAD = "dead"
UNKNOWN = "unknown"
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
]


@dataclass(frozen=True)
class Config:
    request_timeout_seconds: int = 20
    dry_run: bool = False


@dataclass(frozen=True)
class Job:
    title: str
    company: str
    location: str
    link: str
    source: str
    description: str = ""

    @property
    def searchable_text(self) -> str:
        return " ".join([self.title, self.company, self.location, self.source, self.description]).lower()


@dataclass(frozen=True)
class StoredJob:
    title: str
    company: str
    location: str
    link: str
    source: str
    description: str
    is_relevant: bool
    matched_terms: str
    first_seen_at: str
    last_seen_at: str
    alive_status: str = ""
    alive_checked_at: str = ""
    is_hot: bool = False
    hot_terms: str = ""
    requirements: str = ""
    is_new: bool = False


def load_config() -> Config:
    load_dotenv()
    return Config(
        request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "20")),
        dry_run=os.getenv("DRY_RUN", "false").lower() == "true",
    )


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")


def _rtdb_access_token() -> str:
    try:
        from google.auth.transport.requests import Request
        sa_path = os.getenv("FIREBASE_SERVICE_ACCOUNT", "")
        if sa_path:
            from google.oauth2 import service_account
            creds = service_account.Credentials.from_service_account_file(sa_path, scopes=RTDB_SCOPES)
        else:
            import google.auth
            creds, _project_id = google.auth.default(scopes=RTDB_SCOPES)
        creds.refresh(Request())
        return creds.token or ""
    except Exception as exc:  # noqa: BLE001
        logging.warning("Could not obtain Firebase token: %s", exc)
        return ""


def _rtdb_params() -> dict:
    token = _rtdb_access_token()
    return {"access_token": token} if token else {}


def rtdb_get(path: str) -> object:
    try:
        r = requests.get(f"{RTDB_URL}/{path.strip('/')}.json", params=_rtdb_params(), timeout=30)
        if r.status_code == 200:
            return r.json()
        logging.warning("RTDB read /%s failed: HTTP %s %s", path, r.status_code, r.text[:200])
    except requests.RequestException as exc:
        logging.warning("RTDB read /%s failed: %s", path, exc)
    return None


def rtdb_put(path: str, payload: object) -> bool:
    try:
        r = requests.put(f"{RTDB_URL}/{path.strip('/')}.json", params=_rtdb_params(), json=payload, timeout=30)
        if r.status_code == 200:
            return True
        logging.warning("RTDB write /%s failed: HTTP %s %s", path, r.status_code, r.text[:200])
    except requests.RequestException as exc:
        logging.warning("RTDB write /%s failed: %s", path, exc)
    return False


def publish_scan_status(running: bool, message: str, *, requested_at: str = "", finished_at: str = "", count: int | None = None, new_count: int | None = None) -> None:
    payload = {
        "running": running,
        "message": message,
        "requestedAt": requested_at,
        "finishedAt": finished_at,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    if count is not None:
        payload["count"] = count
    if new_count is not None:
        payload["newCount"] = new_count
    rtdb_put("scan_status", payload)


def _headers(referer: str = "https://www.google.com/") -> dict[str, str]:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,he;q=0.8",
        "Referer": referer,
    }


def _clean(value: str) -> str:
    return " ".join((value or "").split()).strip()


def _has_negative_term(text: str) -> bool:
    for neg in NEGATIVE_TERMS:
        if neg.isascii():
            if re.search(rf"\b{re.escape(neg.strip())}\b", text):
                return True
        elif neg in text:
            return True
    return False


def is_relevant_job(job: Job) -> bool:
    text = job.searchable_text
    if _has_negative_term(text):
        return False
    keyword_match = any(kw in text for kw in KEYWORDS)
    location_match = any(loc in text for loc in LOCATIONS)
    role_match = any(role.lower() in text for role in TARGET_ROLES)
    return location_match and (keyword_match or role_match)


def find_matched_terms(job: Job) -> list[str]:
    text = job.searchable_text
    terms = [t for t in KEYWORDS + LOCATIONS if t in text]
    roles = [r for r in TARGET_ROLES if r.lower() in text]
    return sorted(set(terms + roles), key=str.lower)


def evaluate_hotness(text: str) -> tuple[bool, list[str]]:
    low = (text or "").lower()
    fields = [f for f in MED_ENG_FIELDS if f in low]
    if not fields or not any(d in low for d in DEGREE_WORDS):
        return False, []
    return True, fields


def analyze_moran_fit(job: StoredJob) -> tuple[str, str]:
    text = " ".join([job.title, job.company, job.location, job.source, job.description, job.matched_terms, job.hot_terms, job.requirements]).lower()
    if _has_negative_term(text):
        return "skip", "המשרה נראית בכירה/סטודנטיאלית מדי ולכן לא מוצגת כהתאמה."
    signals: list[str] = []
    score = 0
    if job.is_hot or evaluate_hotness(text)[0]:
        signals.append("דורשת תואר בהנדסה רפואית/ביו-רפואית")
        score += 4
    if any(t in text for t in ["medical device", "medical devices", "medical engineering", "biomedical", "מכשור רפואי"]):
        signals.append("נוגעת למכשור רפואי או הנדסה רפואית")
        score += 2
    if any(t in text for t in ["mechanical", "solidworks", "cad", "3d printing", "design", "מכונות"]):
        signals.append("כוללת מכניקה/תכן/CAD שמתאימים לניסיון של מורן")
        score += 2
    if any(t in text for t in ["bioreactor", "cell culture", "tissue culture", "bioprocess", "lab technician", "laboratory"]):
        signals.append("כוללת מעבדה/תרביות תאים/ביופרוסס")
        score += 2
    if any(role.lower() in text for role in TARGET_ROLES):
        signals.append("שם התפקיד קרוב לכיוון המקצועי המבוקש")
        score += 1
    if any(loc in text for loc in LOCATIONS):
        signals.append("המשרה בישראל")
        score += 1
    if any(t in text for t in ["junior", "entry level", "graduate", "0-2", "0-3", "ברמת מתחילים"]):
        signals.append("נראית מתאימה לרמת ג'וניור/בוגרת")
        score += 1
    if not signals and job.matched_terms:
        signals.append(f"זוהו מילות התאמה: {job.matched_terms}")
        score += 1
    if score >= 4:
        return "fit", "מתאימה למורן כי " + "; ".join(signals[:4]) + "."
    if score >= 2 or job.is_relevant:
        return "review", "פחות חזקה, אבל שווה בדיקה כי " + "; ".join(signals[:3]) + "."
    return "skip", "לא נמצאו מספיק סימנים שמחברים את המשרה לפרופיל של מורן."


def _parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat((value or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def _applied_links() -> set[str]:
    applied = rtdb_get("applied")
    if not isinstance(applied, dict):
        return set()
    return {str(v["link"]) for v in applied.values() if isinstance(v, dict) and v.get("link")}


def should_publish_job(job: StoredJob, applied_links: set[str]) -> bool:
    if job.link in applied_links:
        return True
    first_seen = _parse_iso(job.first_seen_at)
    if first_seen is None:
        return True
    if first_seen.tzinfo is None:
        first_seen = first_seen.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - first_seen <= timedelta(days=JOB_RETENTION_DAYS)


def job_record_id(link: str) -> str:
    return hashlib.sha1(link.strip().encode("utf-8")).hexdigest()


def _stored(record: dict) -> StoredJob:
    return StoredJob(
        title=str(record.get("title", "")), company=str(record.get("company", "")),
        location=str(record.get("location", "")), link=str(record.get("link", "")),
        source=str(record.get("source", "")), description=str(record.get("description", "")),
        is_relevant=bool(record.get("is_relevant", False)), matched_terms=str(record.get("matched_terms", "")),
        first_seen_at=str(record.get("first_seen_at", "")), last_seen_at=str(record.get("last_seen_at", "")),
        alive_status=str(record.get("alive_status", "")), alive_checked_at=str(record.get("alive_checked_at", "")),
        is_hot=bool(record.get("is_hot", False)), hot_terms=str(record.get("hot_terms", "")),
        requirements=str(record.get("requirements", "")), is_new=bool(record.get("is_new", False)),
    )


def _public_payload(job: StoredJob, category: str, reason: str) -> dict:
    return {
        "title": job.title, "company": job.company, "location": job.location,
        "link": job.link, "source": job.source, "matched_terms": job.matched_terms,
        "alive_status": job.alive_status, "is_hot": job.is_hot, "hot_terms": job.hot_terms,
        "requirements": job.requirements, "fit_category": category, "fit_reason": reason,
        "is_new": job.is_new, "first_seen_at": job.first_seen_at, "last_seen_at": job.last_seen_at,
    }


def _dedupe(jobs: list[Job]) -> list[Job]:
    seen: set[str] = set()
    result: list[Job] = []
    for job in jobs:
        if job.link and job.link not in seen:
            seen.add(job.link)
            result.append(job)
    return result


def _parse_linkedin(html: str) -> list[Job]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[Job] = []
    for card in soup.select("li, .base-card"):
        link = card.select_one("a.base-card__full-link, a[href*='/jobs/view/']")
        if not link or not link.get("href"):
            continue
        href = link["href"].split("?", 1)[0]
        title = _clean((card.select_one(".base-search-card__title") or card.select_one("h3") or card).get_text(" "))
        company = _clean((card.select_one(".base-search-card__subtitle") or card.select_one("h4") or BeautifulSoup("<x>LinkedIn</x>", "html.parser")).get_text(" "))
        location = _clean((card.select_one(".job-search-card__location") or BeautifulSoup("<x>Israel</x>", "html.parser")).get_text(" "))
        if title and href:
            jobs.append(Job(title, company or "LinkedIn", location or "Israel", href, "LinkedIn"))
    return jobs


def scrape_linkedin(config: Config) -> list[Job]:
    jobs: list[Job] = []
    for keyword in LINKEDIN_KEYWORDS:
        for page in range(LINKEDIN_PAGES):
            params = f"keywords={quote_plus(keyword)}&location=Israel&f_TPR={LINKEDIN_PAST_MONTH}&start={page * 25}"
            url = f"{LINKEDIN_GUEST_URL}?{params}"
            try:
                r = requests.get(url, headers=_headers(), timeout=config.request_timeout_seconds)
                if r.status_code == 200:
                    jobs.extend(_parse_linkedin(r.text))
                elif r.status_code in (429, 999):
                    time.sleep(3)
            except requests.RequestException as exc:
                logging.warning("LinkedIn scrape failed for %s: %s", keyword, exc)
            time.sleep(REQUEST_DELAY_S)
    return jobs


def scrape_greenhouse(config: Config) -> list[Job]:
    jobs: list[Job] = []
    for company in GREENHOUSE_COMPANIES:
        url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true"
        try:
            r = requests.get(url, headers=_headers(), timeout=config.request_timeout_seconds)
            if r.status_code != 200:
                continue
            for item in r.json().get("jobs", []):
                title = _clean(item.get("title", ""))
                link = item.get("absolute_url", "")
                loc = _clean((item.get("location") or {}).get("name", "Israel"))
                content = BeautifulSoup(item.get("content", ""), "html.parser").get_text(" ")[:1000]
                if title and link:
                    jobs.append(Job(title, company.title(), loc or "Israel", link, "Greenhouse", content))
        except Exception as exc:  # noqa: BLE001
            logging.warning("Greenhouse scrape failed for %s: %s", company, exc)
    return jobs


def scrape_all(config: Config) -> list[Job]:
    return _dedupe(scrape_linkedin(config) + scrape_greenhouse(config))


def _classify_alive(link: str, status_code: int, final_url: str, text: str) -> str:
    if status_code in (404, 410):
        return DEAD
    if status_code in (403, 429, 999) or status_code >= 400:
        return UNKNOWN
    low = (text or "").lower()
    if "greenhouse.io/" in link.lower() and "/jobs/" not in final_url.lower():
        return DEAD
    if any(marker in low for marker in DEAD_MARKERS):
        return DEAD
    return ALIVE


def _extract_requirements(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    node = soup.select_one("#content, .content, #app_body, .opening, main, article, .show-more-less-html__markup")
    text = node.get_text("\n") if node else soup.get_text("\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)[:6000]


def inspect_job(link: str, timeout: int = 15) -> dict:
    target = link
    if "linkedin.com/jobs/view/" in link.lower():
        match = re.search(r"(\d{6,})(?:\D*)$", link)
        if match:
            target = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/" + match.group(1)
    try:
        r = requests.get(target, headers=_headers(), timeout=timeout, allow_redirects=True)
    except requests.RequestException:
        return {"status": UNKNOWN, "is_hot": False, "hot_terms": [], "requirements": ""}
    status = _classify_alive(link, r.status_code, str(r.url), r.text)
    if r.status_code == 200:
        is_hot, hot_terms = evaluate_hotness(r.text)
        return {"status": status, "is_hot": is_hot, "hot_terms": hot_terms, "requirements": _extract_requirements(r.text)}
    return {"status": status, "is_hot": False, "hot_terms": [], "requirements": ""}


def build_public_jobs(state: dict[str, dict], applied: set[str]) -> list[dict]:
    public: list[dict] = []
    for record in state.values():
        if not isinstance(record, dict):
            continue
        job = _stored(record)
        if not job.link or job.alive_status == DEAD or not should_publish_job(job, applied):
            continue
        category, reason = analyze_moran_fit(job)
        if category != "skip":
            public.append(_public_payload(job, category, reason))
    return sorted(public, key=lambda j: (not j.get("is_new", False), j.get("fit_category") != "fit", not j.get("is_hot", False), str(j.get("last_seen_at", ""))))


def push_public_feed(public_jobs: list[dict], generated_at: str) -> bool:
    ok_jobs = rtdb_put("jobs", public_jobs)
    ok_meta = rtdb_put("meta", {"generated_at": generated_at, "count": len(public_jobs)})
    return ok_jobs and ok_meta


def run_cloud_scan(config: Config, use_sample: bool = False) -> dict[str, int]:
    now = datetime.now(timezone.utc).isoformat()
    existing_raw = rtdb_get("job_state")
    state: dict[str, dict] = existing_raw if isinstance(existing_raw, dict) else {}
    applied = _applied_links()

    raw_jobs = scrape_all(config)
    relevant = [job for job in _dedupe(raw_jobs) if is_relevant_job(job)]
    scraped_ids = {job_record_id(job.link) for job in relevant}

    next_state: dict[str, dict] = {}
    for job_id, record in state.items():
        if isinstance(record, dict):
            next_state[job_id] = {**record, "is_new": False}

    new_relevant = 0
    for job in relevant:
        job_id = job_record_id(job.link)
        existing = next_state.get(job_id, {})
        if not existing:
            new_relevant += 1
        inspection = inspect_job(job.link, config.request_timeout_seconds)
        next_state[job_id] = {
            **existing,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "link": job.link,
            "source": job.source,
            "description": job.description,
            "is_relevant": True,
            "matched_terms": ", ".join(find_matched_terms(job)),
            "first_seen_at": str(existing.get("first_seen_at") or now),
            "last_seen_at": now,
            "alive_status": inspection["status"],
            "alive_checked_at": now,
            "is_hot": bool(inspection["is_hot"]),
            "hot_terms": ", ".join(sorted(set(inspection["hot_terms"]))),
            "requirements": inspection["requirements"] or str(existing.get("requirements", "")),
            "is_new": not bool(existing),
        }

    pruned: dict[str, dict] = {}
    for job_id, record in next_state.items():
        stored = _stored(record)
        if job_id in scraped_ids or should_publish_job(stored, applied):
            pruned[job_id] = record

    public_jobs = build_public_jobs(pruned, applied)
    rtdb_put("job_state", pruned)
    push_public_feed(public_jobs, now)
    return {"scraped": len(relevant), "new_relevant": new_relevant, "published": len(public_jobs), "state": len(pruned)}


if __name__ == "__main__":
    setup_logging()
    print(run_cloud_scan(load_config()))
