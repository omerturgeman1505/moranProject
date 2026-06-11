"""
Automated job search, filtering, and tracking platform.

NO-API direct web scraping: fetches and parses raw HTML straight from job
boards (LinkedIn public guest search + Greenhouse public boards) with rotating
browser-like headers. No Google API, SerpApi, or paid endpoints are used.

Setup:
  1. pip install -r requirements.txt
  2. python job_search_platform.py [--sample] [--dry-run] [--no-verify]

Web dashboard:
  python web_app.py  →  http://127.0.0.1:5050
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import random
import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Iterator
from urllib.parse import quote_plus, unquote_plus, urljoin

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from gemini_fit import assess_job_with_gemini
from job_sections import parse_job_summary

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    gspread = None
    Credentials = None


# ---------------------------------------------------------------------------
# Candidate profile — update these when CV is provided
# ---------------------------------------------------------------------------

# Keyword searches run against LinkedIn's public guest job-search endpoint.
# Each is searched across Israel and restricted to the last month at fetch time.
LINKEDIN_KEYWORDS = [
    "Junior R&D Engineer",
    "R&D Lab Technician",
    "R&D Engineer",
    "Biomedical Engineer",
    "Medical Engineer",
    "Medical Device Engineer",
    "Mechanical Engineer",
    "Junior Mechanical Engineer",
    "Lab Technician",
    "R&D Technician",
    "Process Engineer",
    "Bioprocess Engineer",
    "Integration Engineer",
    "System Integration Engineer",
    "NPI Engineer",
    "Bioreactor Engineer",
    "Cell Culture Engineer",
    "Mechanical Design Engineer",
    "Validation Engineer",
    "V&V Engineer Medical Devices",
    "Biomedical V&V Engineer",
    "Process Validation Engineer Medical Device",
    "R&D Lab Engineer Medical Device",
    "Junior Biomedical Engineer",
    "Junior Medical Device Engineer",
    "Manufacturing Engineer Medical Device",
    "Application Engineer Medical Device",
    "מהנדס מכשור רפואי",
    "מהנדסת מכשור רפואי",
    "מהנדס מכונות",
    "מהנדסת מכונות",
    "מהנדס פיתוח",
    "מהנדסת פיתוח",
]

# Israeli companies with public Greenhouse boards, fetched via the structured
# JSON API (boards-api.greenhouse.io). A mix of medtech / biotech / hardware.
GREENHOUSE_COMPANIES = [
    "medtronic",    # Global medtech leader, large Israel R&D center
    "insightec",    # Focused ultrasound / therapeutic ultrasound
    "nanox",        # Nano-X Imaging — medical X-ray
    "evogene",      # Plant biotech / genomics
    "pluri",        # Stem cell / cell therapy (Rehovot)
    "collplant",    # Regenerative medicine / bioprinting
    "lumenis",      # Medical lasers
    "rapidmedical", # Neurovascular devices
]

# Optional dynamic-render boards (Comeet/Workday) handled via Playwright when
# installed; otherwise skipped gracefully.
DYNAMIC_BOARDS: list[str] = []

TARGET_ROLES = [
    "Junior R&D Engineer",
    "Junior Engineer",
    "R&D Engineer",
    "R&D Lab Technician",
    "R&D Technician",
    "Lab Technician",
    "Mechanical Engineer",
    "Mechanical Design Engineer",
    "Biomedical Engineer",
    "Medical Engineer",
    "Medical Device Engineer",
    "Process Engineer",
    "Bioprocess Engineer",
    "Integration Engineer",
    "System Integration Engineer",
    "NPI Engineer",
    "Validation Engineer",
    "Manufacturing Engineer",
    "Application Engineer",
    "מהנדס",
    "מהנדסת",
    "מהנדס פיתוח",
    "מהנדסת פיתוח",
]

# Core skills/domains from Moran's CV (medical devices + cultivated cells /
# bioprocess) — used for client-side relevance matching of titles & text.
KEYWORDS = [
    # Mechanical / design
    "solidworks", "mechanical design", "cad", "3d printing", "matlab", "python",
    "prototype", "prototyping", "mechanical engineer", "r&d", "npi", "integration",
    "troubleshooting", "machine systems", "custom machine", "equipment",
    # Medical devices
    "medical device", "medical devices", "medical engineer", "medical engineering",
    "biomedical engineer", "biomedical engineering", "physiologic", "physiological",
    "מכשור רפואי", "מהנדס", "מהנדסת",
    # Bioprocess / cultivated cells / lab
    "bioreactor", "bioreactors", "cell culture", "cultivated", "tissue culture",
    "bioprocess", "biotech", "foodtech", "food tech", "lab technician",
    "process engineer", "process optimization", "validation", "sop", "work instructions",
    "sterile", "laboratory", "lab equipment", "data analysis",
    # Moran's specific lab systems
    "mfcs", "dot system", "dot systems", "flexcell", "trubio",
    "cellaca", "cedex", "bioanalyzer", "masterflex", "toc analyzer",
    "ionex", "wintercell", "twin", "large scale cell culture",
    "water saving", "calibration", "calibrated",
    # Moran's final project
    "iud", "inserter", "removal device", "spiral iud", "afeka",
]

LOCATIONS = [
    "rehovot",
    "רחובות",
    "tel aviv",
    "תל אביב",
    "jerusalem",
    "ירושלים",
    "haifa",
    "חיפה",
    "beer sheba",
    "be'er sheva",
    "באר שבע",
    "israel",
    "ישראל",
]

# Jobs containing these words are never considered relevant. Per spec, Senior
# and Student/Intern tracks are excluded for this junior-graduate profile.
NEGATIVE_TERMS = [
    "senior", "lead", "manager", "director", "head of", "vp ",
    "principal", "staff engineer", "team lead",
    "student", "intern", "internship",
    "freelance", "freelancer", "ai trainer", "trainer", "data annotation",
    "annotator", "content writer",
    "simulator", "simulation", "simulations", "gaming", "game engine",
    "unity", "unreal", "vr", "machine learning", "big data", "cloud",
    "wireless", "silicon", "soc", "mac layer", "bluetooth", "ble", "firmware",
    "signal processing", "software engineer", "software engineering",
    "algorithm development", "data scientist", "data science",
    "production worker", "manual dexterity", "production optics employee",
    "סימולטור", "סימולטורים", "סימולציה", "סימולציות", "מנועים גרפיים",
    "למידת מכונה", "מציאות מדומה",
    "מנהל", "מנהלת", "סטודנט", "סטודנטית", "מתמחה",
    "בכיר", "בכירה", "מנוסה",
    # Title-level only (also added to LEVEL_NEGATIVE_TERMS)
    "sr",
    "תוכנה",
    "software",
    "sysops",
    "data center",
    "chip",
    "pcb",
    # Body-level: hardware / embedded / unrelated domains
    "fpga", "hardware engineer", "hardware engineering",
    "מהנדס תוכנה", "מהנדסת תוכנה",
]
LEVEL_NEGATIVE_TERMS = {
    "senior", "lead", "manager", "director", "head of", "vp ",
    "principal", "staff engineer", "team lead",
    "מנהל", "מנהלת", "סטודנט", "סטודנטית", "מתמחה",
    "בכיר", "בכירה", "מנוסה",
    "sr",
    "תוכנה",
    "software",
    "sysops",
    "data center",
    "chip",
    "pcb",
}


# ---------------------------------------------------------------------------
# Constants & HTTP session simulation
# ---------------------------------------------------------------------------

LINKEDIN_GUEST_URL = (
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
)
LINKEDIN_PAST_MONTH = "r2592000"   # f_TPR value = last 30 days (in seconds)
LINKEDIN_PAGES = 5                 # 25 results each → up to 125 per keyword
REQUEST_DELAY_S = 1.5              # Polite delay between requests (avoid 429s)
SEEN_JSON_PATH = "jobs_seen.json"  # Lightweight dedup store (per spec)
JOB_RETENTION_DAYS = 7             # Drop old non-applied dashboard jobs.

CAREER_PAGES = [
    # ── Existing ──────────────────────────────────────────────────────────────
    {
        "company": "Admetec",
        "url": "https://www.admetec.com/careers/",
        "domain": "Medical Device",
    },
    {
        "company": "Adin Dental Implant Systems",
        "url": "https://www.adin-implants.com/adin-careers/",
        "domain": "Medical Device",
    },
    {
        "company": "Gsap",
        "url": "https://gsap.co.il/en/careers/",
        "domain": "Medical Devices / Biotech / Validation",
    },
    {
        "company": "Magenta Medical",
        "url": "https://www.comeet.com/jobs/magentamed/F9.003",
        "domain": "Medical Device",
    },
    {
        "company": "Inovytec",
        "url": "https://www.inovytec.com/careers/",
        "domain": "Medical Device",
    },
    {
        "company": "Envizion Medical",
        "url": "https://www.envizionmed.com/find-a-career/",
        "domain": "Medical Device",
    },
    {
        "company": "Medoc",
        "url": "https://www.medoc-web.com/careers",
        "domain": "Medical Device",
    },
    {
        "company": "Alpha Omega",
        "url": "https://www.alphaomega-eng.com/Israel",
        "domain": "Medical Device",
    },
    # ── Cultivated Meat / Cell Culture / Bioprocess ───────────────────────────
    # Directly relevant to Moran's bioreactor + large-scale cell culture experience
    {
        "company": "Aleph Farms",
        "url": "https://aleph-farms.com/jobs/",
        "domain": "Cultivated Meat / Cell Culture / Bioprocess",
    },
    {
        "company": "Believer Meats",
        "url": "https://believermeats.com/careers/",
        "domain": "Cultivated Meat / Cell Culture / Bioreactor",
    },
    {
        "company": "SuperMeat",
        "url": "https://supermeat.com/careers/",
        "domain": "Cultivated Meat / Cell Culture",
    },
    {
        "company": "Remilk",
        "url": "https://remilk.com/careers",
        "domain": "Precision Fermentation / Bioprocess",
    },
    {
        "company": "Forsea Foods",
        "url": "https://www.forsea.co/careers/",
        "domain": "Cultivated Seafood / Cell Culture",
    },
    {
        "company": "Steakholder Foods",
        "url": "https://www.steakholder.com/careers",
        "domain": "Cultivated Meat / 3D Bioprinting",
    },
    {
        "company": "BioBetter",
        "url": "https://biobetter.com/careers/",
        "domain": "Agri-Biotech / Plant-based Biologics",
    },
    # ── Medical Device / MedTech ──────────────────────────────────────────────
    {
        "company": "Lumenis",
        "url": "https://www.lumenis.com/company/careers/",
        "domain": "Medical Laser / Medical Device",
    },
    {
        "company": "CollPlant",
        "url": "https://www.collplant.com/company/careers/",
        "domain": "Regenerative Medicine / Bioprinting / Medical Device",
    },
    {
        "company": "Rapid Medical",
        "url": "https://www.rapid-medical.com/careers/",
        "domain": "Neurovascular Medical Device",
    },
    {
        "company": "BrainsWay",
        "url": "https://www.brainsway.com/careers/",
        "domain": "Neurostimulation / Medical Device",
    },
    {
        "company": "Microbot Medical",
        "url": "https://microbotmedical.com/careers/",
        "domain": "Surgical Robotics / Medical Device",
    },
    {
        "company": "Medinol",
        "url": "https://www.medinol.com/careers/",
        "domain": "Cardiovascular / Coronary Medical Device",
    },
    {
        "company": "Todos Medical",
        "url": "https://www.todosmedical.com/careers/",
        "domain": "Medical Diagnostics / Medical Device",
    },
    {
        "company": "Oramed Pharmaceuticals",
        "url": "https://www.oramed.com/careers/",
        "domain": "Oral Drug Delivery / Pharmaceutical",
    },
    {
        "company": "Nano Dimension",
        "url": "https://www.nano-di.com/careers",
        "domain": "3D Printing / Electronics / Medtech",
    },
    {
        "company": "InVivo Therapeutics",
        "url": "https://www.invivotherapeutics.com/careers/",
        "domain": "Spinal Cord / Biomaterials / Medical Device",
    },
    {
        "company": "Itamar Medical",
        "url": "https://jobs.lever.co/itamarmedical",
        "domain": "Cardiovascular Diagnostics / Medical Device",
    },
    {
        "company": "Nucleai",
        "url": "https://nucleai.ai/careers/",
        "domain": "AI Pathology / Medical Device / Biomedical",
    },
    {
        "company": "PhotoSmart",
        "url": "https://www.photosmartmed.com/careers",
        "domain": "Photoacoustic Imaging / Medical Device",
    },
    {
        "company": "OR-Nim Medical",
        "url": "https://www.or-nim.com/careers/",
        "domain": "Non-invasive Monitoring / Medical Device",
    },
]

# Firebase Realtime Database — jobs are pushed here so the dashboard reads live
# data without re-importing/re-deploying. Override with FIREBASE_RTDB_URL.
RTDB_URL = os.getenv(
    "FIREBASE_RTDB_URL",
    "https://moran-cce72-default-rtdb.europe-west1.firebasedatabase.app",
).rstrip("/")

_RTDB_SCOPES = [
    "https://www.googleapis.com/auth/firebase.database",
    "https://www.googleapis.com/auth/userinfo.email",
]


def _rtdb_access_token() -> str:
    """Mint a short-lived admin access token from the service account, so the
    server can write to RTDB without opening public write rules."""
    sa_path = os.getenv("FIREBASE_SERVICE_ACCOUNT", "")
    try:
        from google.auth.transport.requests import Request as _Req
        if sa_path:
            from google.oauth2 import service_account as _sa
            creds = _sa.Credentials.from_service_account_file(sa_path, scopes=_RTDB_SCOPES)
        else:
            import google.auth
            creds, _project_id = google.auth.default(scopes=_RTDB_SCOPES)
        creds.refresh(_Req())
        return creds.token or ""
    except Exception as exc:  # noqa: BLE001
        logging.warning("Could not obtain Firebase access token: %s", exc)
        return ""


def _rtdb_params() -> dict:
    token = _rtdb_access_token()
    return {"access_token": token} if token else {}


def rtdb_put(path: str, payload: dict | list | str | int | bool | None) -> bool:
    """Write one node to Firebase RTDB using the local service account."""
    path = path.strip("/")
    try:
        resp = requests.put(
            f"{RTDB_URL}/{path}.json", params=_rtdb_params(), json=payload, timeout=30
        )
        if resp.status_code == 200:
            return True
        logging.warning("RTDB write to /%s failed (HTTP %s): %s", path, resp.status_code, resp.text[:200])
    except requests.RequestException as exc:
        logging.warning("RTDB write to /%s failed: %s", path, exc)
    return False


def rtdb_delete(path: str) -> bool:
    """Delete one node from Firebase RTDB using server credentials."""
    path = path.strip("/")
    try:
        resp = requests.delete(
            f"{RTDB_URL}/{path}.json", params=_rtdb_params(), timeout=30
        )
        if resp.status_code == 200:
            return True
        logging.warning("RTDB delete /%s failed (HTTP %s): %s", path, resp.status_code, resp.text[:200])
    except requests.RequestException as exc:
        logging.warning("RTDB delete /%s failed: %s", path, exc)
    return False


def rtdb_get(path: str) -> object:
    """Read one node from Firebase RTDB."""
    path = path.strip("/")
    try:
        resp = requests.get(
            f"{RTDB_URL}/{path}.json", params=_rtdb_params(), timeout=30
        )
        if resp.status_code == 200:
            return resp.json()
        logging.warning("RTDB read from /%s failed (HTTP %s): %s", path, resp.status_code, resp.text[:200])
    except requests.RequestException as exc:
        logging.warning("RTDB read from /%s failed: %s", path, exc)
    return None


def publish_scan_status(
    running: bool,
    message: str,
    *,
    requested_at: str = "",
    finished_at: str = "",
    count: int | None = None,
    new_count: int | None = None,
) -> None:
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

# Rotated to look like distinct real browser sessions and dodge naive 403 blocks.
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
]
ACCEPT_LANGUAGES = [
    "en-US,en;q=0.9,he;q=0.8",
    "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
    "en-GB,en;q=0.9,he;q=0.8",
    "he,en-US;q=0.9,en;q=0.8",
]


def _random_headers(referer: str = "https://www.google.com/") -> dict[str, str]:
    """A realistic, randomized browser-session header set."""
    ua = random.choice(USER_AGENTS)
    headers: dict[str, str] = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": random.choice(ACCEPT_LANGUAGES),
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": referer,
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin" if referer and "linkedin" in referer else "cross-site",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
        "DNT": "1",
    }
    # Add Chrome-specific hint headers when using a Chrome UA
    if "Chrome/" in ua and "Edg/" not in ua:
        ver = ua.split("Chrome/")[1].split(".")[0]
        headers["sec-ch-ua"] = f'"Chromium";v="{ver}", "Google Chrome";v="{ver}", "Not_A Brand";v="8"'
        headers["sec-ch-ua-mobile"] = "?0"
        headers["sec-ch-ua-platform"] = '"Windows"' if "Windows" in ua else '"macOS"'
    return headers


# Backwards-compatible default (used by liveness checker / tests).
DEFAULT_HEADERS = {"User-Agent": USER_AGENTS[0]}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

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
        return " ".join(
            [self.title, self.company, self.location, self.source, self.description]
        ).lower()


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
    alive_status: str = ""        # 'alive' | 'dead' | 'unknown' | ''
    alive_checked_at: str = ""
    is_hot: bool = False          # requires a B.Sc. Medical/Biomedical Eng. degree
    hot_terms: str = ""           # which degree/field terms were found
    requirements: str = ""        # full job-description text from the posting
    is_new: bool = False          # first discovered in the most recent scan


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Config:
    google_api_key: str
    google_cx: str
    sqlite_path: str
    request_timeout_seconds: int
    sheets_enabled: bool
    google_sheet_id: str
    google_sheet_name: str
    google_service_account_file: str
    google_service_account_json: str
    dry_run: bool


def load_config() -> Config:
    load_dotenv()
    return Config(
        google_api_key=os.getenv("GOOGLE_API_KEY", ""),
        google_cx=os.getenv("GOOGLE_CX", ""),
        sqlite_path=os.getenv("SQLITE_PATH", "processed_jobs.sqlite3"),
        request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "20")),
        sheets_enabled=os.getenv("SHEETS_ENABLED", "false").lower() == "true",
        google_sheet_id=os.getenv("GOOGLE_SHEET_ID", ""),
        google_sheet_name=os.getenv("GOOGLE_SHEET_NAME", "Jobs"),
        google_service_account_file=os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", ""),
        google_service_account_json=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", ""),
        dry_run=os.getenv("DRY_RUN", "false").lower() == "true",
    )


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


# ---------------------------------------------------------------------------
# SQLite job store
# ---------------------------------------------------------------------------

class JobStore:
    def __init__(self, sqlite_path: str) -> None:
        self.sqlite_path = sqlite_path
        self._init_db()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.sqlite_path)
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS seen_jobs (
                    link TEXT PRIMARY KEY,
                    title TEXT,
                    company TEXT,
                    source TEXT,
                    seen_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS found_jobs (
                    link TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    company TEXT NOT NULL,
                    location TEXT NOT NULL,
                    source TEXT NOT NULL,
                    description TEXT NOT NULL,
                    is_relevant INTEGER NOT NULL,
                    matched_terms TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    alive_status TEXT NOT NULL DEFAULT '',
                    alive_checked_at TEXT NOT NULL DEFAULT ''
                )
            """)
            # Migrate older databases that predate later columns.
            existing = {row[1] for row in conn.execute("PRAGMA table_info(found_jobs)")}
            for column in ("alive_status", "alive_checked_at", "hot_terms", "requirements"):
                if column not in existing:
                    conn.execute(
                        f"ALTER TABLE found_jobs ADD COLUMN {column} TEXT NOT NULL DEFAULT ''"
                    )
            for int_col in ("is_hot", "is_new"):
                if int_col not in existing:
                    conn.execute(
                        f"ALTER TABLE found_jobs ADD COLUMN {int_col} INTEGER NOT NULL DEFAULT 0"
                    )
            conn.commit()

    def has_seen(self, link: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM seen_jobs WHERE link = ? LIMIT 1", (link,)
            ).fetchone()
        return row is not None

    def mark_seen(self, job: Job) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO seen_jobs (link, title, company, source, seen_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (job.link, job.title, job.company, job.source, now),
            )
            conn.commit()

    def upsert_job(self, job: Job) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO found_jobs (
                    link, title, company, location, source, description,
                    is_relevant, matched_terms, first_seen_at, last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(link) DO UPDATE SET
                    title = excluded.title,
                    company = excluded.company,
                    location = excluded.location,
                    description = excluded.description,
                    is_relevant = excluded.is_relevant,
                    matched_terms = excluded.matched_terms,
                    last_seen_at = excluded.last_seen_at
            """, (
                job.link, job.title, job.company, job.location, job.source,
                job.description,
                1 if is_relevant_job(job) else 0,
                ", ".join(find_matched_terms(job)),
                now, now,
            ))
            conn.commit()

    def update_alive_status(self, link: str, status: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE found_jobs SET alive_status = ?, alive_checked_at = ? WHERE link = ?",
                (status, now, link),
            )
            conn.commit()

    def update_inspection(
        self, link: str, status: str, is_hot: bool, hot_terms: str,
        requirements: str = "",
    ) -> None:
        """Record liveness, 'hot' (degree-match), and requirements from one visit."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            if requirements:
                conn.execute(
                    "UPDATE found_jobs SET alive_status = ?, alive_checked_at = ?, "
                    "is_hot = ?, hot_terms = ?, requirements = ? WHERE link = ?",
                    (status, now, 1 if is_hot else 0, hot_terms, requirements, link),
                )
            else:
                conn.execute(
                    "UPDATE found_jobs SET alive_status = ?, alive_checked_at = ?, "
                    "is_hot = ?, hot_terms = ? WHERE link = ?",
                    (status, now, 1 if is_hot else 0, hot_terms, link),
                )
            conn.commit()

    def list_jobs(self) -> list[StoredJob]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT title, company, location, link, source, description,
                       is_relevant, matched_terms, first_seen_at, last_seen_at,
                       alive_status, alive_checked_at, is_hot, hot_terms, requirements,
                       is_new
                FROM found_jobs
                ORDER BY is_relevant DESC,
                         is_new DESC,
                         is_hot DESC,
                         CASE alive_status WHEN 'alive' THEN 0 WHEN 'unknown' THEN 1
                                           WHEN '' THEN 2 ELSE 3 END,
                         last_seen_at DESC
            """).fetchall()
        return [
            StoredJob(
                title=r["title"], company=r["company"], location=r["location"],
                link=r["link"], source=r["source"], description=r["description"],
                is_relevant=bool(r["is_relevant"]), matched_terms=r["matched_terms"],
                first_seen_at=r["first_seen_at"], last_seen_at=r["last_seen_at"],
                alive_status=r["alive_status"], alive_checked_at=r["alive_checked_at"],
                is_hot=bool(r["is_hot"]), hot_terms=r["hot_terms"],
                requirements=r["requirements"], is_new=bool(r["is_new"]),
            )
            for r in rows
        ]

    def existing_links(self) -> set[str]:
        with self._connect() as conn:
            return {r[0] for r in conn.execute("SELECT link FROM found_jobs")}

    def set_new_flags(self, new_links: set[str]) -> None:
        """Mark the given links as new (is_new=1) and everything else as old."""
        with self._connect() as conn:
            conn.execute("UPDATE found_jobs SET is_new = 0")
            for link in new_links:
                conn.execute("UPDATE found_jobs SET is_new = 1 WHERE link = ?", (link,))
            conn.commit()

    def count_jobs(self) -> tuple[int, int]:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM found_jobs").fetchone()[0]
            relevant = conn.execute(
                "SELECT COUNT(*) FROM found_jobs WHERE is_relevant = 1"
            ).fetchone()[0]
        return total, relevant

    def count_live_relevant(self) -> int:
        with self._connect() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM found_jobs "
                "WHERE is_relevant = 1 AND alive_status IN ('alive', 'unknown')"
            ).fetchone()[0]

    def count_hot(self) -> int:
        with self._connect() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM found_jobs WHERE is_relevant = 1 AND is_hot = 1"
            ).fetchone()[0]

    def relevant_links(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT link FROM found_jobs WHERE is_relevant = 1"
            ).fetchall()
        return [r[0] for r in rows]

    def reclassify_all(self) -> int:
        """Recompute is_relevant/matched_terms for every stored job (after a
        filter change) without re-scraping. Returns the relevant count."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT title, company, location, link, source, description FROM found_jobs"
            ).fetchall()
            relevant = 0
            for r in rows:
                job = Job(r["title"], r["company"], r["location"], r["link"],
                          r["source"], r["description"])
                is_rel = is_relevant_job(job)
                relevant += int(is_rel)
                conn.execute(
                    "UPDATE found_jobs SET is_relevant = ?, matched_terms = ? WHERE link = ?",
                    (1 if is_rel else 0, ", ".join(find_matched_terms(job)), r["link"]),
                )
            conn.commit()
        return relevant


# ---------------------------------------------------------------------------
# Relevance logic
# ---------------------------------------------------------------------------

def _has_negative_term(text: str) -> bool:
    """Match negatives on word boundaries for ASCII terms (so 'lead' doesn't
    hit 'leadership' spuriously); substring match for Hebrew terms."""
    for neg in NEGATIVE_TERMS:
        if neg.isascii():
            if re.search(rf"\b{re.escape(neg.strip())}\b", text):
                return True
        elif neg in text:
            return True
    return False


def _has_job_level_negative(job: Job | StoredJob) -> bool:
    title_text = " ".join([job.title, job.company]).lower()
    if _has_negative_term(title_text):
        return True

    body_text = " ".join([
        getattr(job, "location", ""),
        getattr(job, "source", ""),
        getattr(job, "description", ""),
        getattr(job, "matched_terms", ""),
        getattr(job, "hot_terms", ""),
        getattr(job, "requirements", ""),
    ]).lower()
    recruiter_noise = [
        "senior talent acquisition", "talent acquisition partner",
        "recruitment services", "career growth consultant",
    ]
    for phrase in recruiter_noise:
        body_text = body_text.replace(phrase, "")
    recent_grad = "recently graduated" in body_text or "graduate" in body_text
    biomedical = any(term in body_text for term in ["biomedical", "medical device", "medical engineering"])
    for neg in NEGATIVE_TERMS:
        if neg in LEVEL_NEGATIVE_TERMS:
            continue
        if neg == "student" and recent_grad and biomedical:
            continue
        if neg.isascii():
            if re.search(rf"\b{re.escape(neg.strip())}\b", body_text):
                return True
        elif neg in body_text:
            return True
    return False


def is_relevant_job(job: Job) -> bool:
    text = job.searchable_text
    if _has_job_level_negative(job):
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


# ---------------------------------------------------------------------------
# "Hot" detection — a posting whose requirements ask for Moran's degree:
# a B.Sc. in Medical / Biomedical Engineering.
# ---------------------------------------------------------------------------

# Moran's exact field of study (Medical Engineering == Biomedical Engineering).
MED_ENG_FIELDS = [
    "biomedical engineering", "bio-medical engineering", "bio medical engineering",
    "medical engineering", "medical engineer", "biomedical engineer",
    "הנדסה רפואית", "הנדסה ביו-רפואית", "הנדסה ביורפואית", "הנדסה ביו רפואית",
]
# Degree indicators that confirm it's an academic requirement, not a team name.
DEGREE_WORDS = [
    "b.sc", "bsc", "b.s.", "b.eng", "beng", "bachelor", "b.a.", "degree",
    "תואר", "בוגר", "בוגרת", "ב.סק",
]

HOT_PROFILE_SIGNALS = {
    "r_and_d": [
        "r&d", "research and development", "development engineer",
        "פיתוח",
    ],
    "junior_level": [
        "junior", "entry level", "graduate", "0-2", "0-3", "1-2", "1-3",
        "b.sc", "bsc", "bachelor", "תואר", "בוגר", "בוגרת",
    ],
    "medical_domain": [
        "medical device", "medical devices", "medical engineering",
        "biomedical", "physiologic", "physiological", "מכשור רפואי", "הנדסה רפואית",
        "iso 13485", "design control", "clinical", "implant", "catheter",
        "surgical", "patient monitoring", "diagnostics",
        "ציוד רפואי", "אביזר רפואי", "שתלים", "קליני", "קלינית",
        "הנדסה ביו רפואית", "הנדסה ביו-רפואית", "הנדסה ביורפואית",
    ],
    "mechanical_design": [
        "solidworks", "cad", "mechanical design", "3d printing",
        "prototype", "prototyping", "mechanical", "iud", "inserter",
        "removal device", "מכונות",
    ],
    "lab_bioprocess": [
        "bioreactor", "bioreactors", "cell culture", "tissue culture",
        "bioprocess", "cultivated", "sterile", "laboratory", "lab technician",
        "flexcell", "trubio", "cellaca", "cedex", "mfcs", "masterflex",
        "dot system", "dot systems", "twin", "large scale cell culture",
        "calibration", "calibrated",
    ],
    "process_data": [
        "process optimization", "process engineer", "validation", "sop",
        "work instructions", "data analysis",
    ],
    "systems_integration": [
        "system integration", "machine systems", "custom machine",
        "troubleshooting", "maintenance", "lab equipment", "reliability", "repeatability",
    ],
}


def evaluate_hotness(text: str) -> tuple[bool, list[str]]:
    """A job is 'hot' for Moran when it either asks for her exact degree or
    combines several strong signals from her CV."""
    if not text:
        return False, []
    low = text.lower()
    fields = [f for f in MED_ENG_FIELDS if f in low]
    if fields and any(d in low for d in DEGREE_WORDS):
        return True, fields

    matched_groups: list[str] = []
    for group, terms in HOT_PROFILE_SIGNALS.items():
        if any(term in low for term in terms):
            matched_groups.append(group)

    strong_groups = {
        "medical_domain", "mechanical_design", "lab_bioprocess",
        "process_data", "systems_integration",
    }
    has_role_or_level = bool({"r_and_d", "junior_level"} & set(matched_groups))
    strong_count = len(strong_groups & set(matched_groups))
    if strong_count >= 2 and (has_role_or_level or "medical_domain" in matched_groups):
        return True, matched_groups
    if strong_count >= 3:
        return True, matched_groups
    return False, []


def _has_biomedical_review_signal(text: str) -> bool:
    low = (text or "").lower()
    medical = any(term in low for term in HOT_PROFILE_SIGNALS["medical_domain"])
    if not medical:
        return False
    review_terms = (
        HOT_PROFILE_SIGNALS["lab_bioprocess"]
        + HOT_PROFILE_SIGNALS["process_data"]
        + HOT_PROFILE_SIGNALS["mechanical_design"]
        + ["v&v", "verification", "medical devices", "quality control"]
    )
    return any(term in low for term in review_terms)


def _clean_job_requirement_text(text: str) -> str:
    """Remove LinkedIn recruiter/profile preamble that is not job requirements."""
    noise_markers = [
        "direct message the job poster",
        "הודעה ישירה פוסטר עבודה",
        "talent acquisition",
        "recruitment",
        "career growth consultant",
        "vp hr",
        "vp r&d",
        "co-founder",
        "years in medtech innovation",
        "people first",
    ]
    kept: list[str] = []
    for line in (text or "").splitlines():
        low = line.lower()
        if any(marker in low for marker in noise_markers):
            continue
        kept.append(line)
    return "\n".join(kept)


def analyze_moran_fit(job: StoredJob) -> tuple[str, str]:
    """Classify a stored posting for Moran and explain the decision."""
    clean_requirements = _clean_job_requirement_text(job.requirements)
    text = " ".join([
        job.title, job.company, job.location, job.source, job.description,
        job.matched_terms, job.hot_terms, clean_requirements,
    ]).lower()
    if _has_job_level_negative(job):
        return "skip", "המשרה נראית בכירה/סטודנטיאלית מדי ולכן לא מוצגת כהתאמה."

    signals: list[str] = []
    score = 0
    if job.is_hot or evaluate_hotness(text)[0]:
        signals.append("מכילה שילוב חזק של דרישות שמתאים לפרופיל של מורן")
        score += 4
    if any(term in text for term in HOT_PROFILE_SIGNALS["medical_domain"]):
        signals.append("נוגעת למכשור רפואי או הנדסה רפואית")
        score += 3
    if any(term in text for term in HOT_PROFILE_SIGNALS["mechanical_design"]):
        signals.append("כוללת מכניקה/תכן/CAD שמתאימים לניסיון של מורן")
        score += 3
    if any(term in text for term in HOT_PROFILE_SIGNALS["lab_bioprocess"]):
        signals.append("כוללת מעבדה/ביוריאקטורים/תרביות תאים או ציוד שמוכר לה")
        score += 3
    if any(term in text for term in HOT_PROFILE_SIGNALS["systems_integration"]):
        signals.append("דורשת אינטגרציה, פתרון תקלות או עבודה עם מערכות מכניות מורכבות")
        score += 2
    if any(term in text for term in HOT_PROFILE_SIGNALS["process_data"]):
        signals.append("מתחברת לניסיון שלה באופטימיזציית תהליך, SOPs וניתוח נתונים")
        score += 2
    specific_roles = [role for role in TARGET_ROLES if role.lower() not in {"מהנדס", "מהנדסת"}]
    if any(role.lower() in text for role in specific_roles):
        signals.append("שם התפקיד קרוב לכיוון המקצועי המבוקש")
        score += 2
    if any(loc in text for loc in LOCATIONS):
        signals.append("המשרה בישראל")
        score += 1
    if any(term in text for term in HOT_PROFILE_SIGNALS["junior_level"]):
        signals.append("נראית מתאימה לרמת ג'וניור/בוגרת")
        score += 2
    if not signals and job.matched_terms:
        signals.append(f"זוהו מילות התאמה: {job.matched_terms}")
        score += 1

    if score >= 4:
        category, reason = "fit", "מתאימה למורן כי " + "; ".join(signals[:4]) + "."
    elif score >= 2 or job.is_relevant:
        category, reason = "review", "פחות חזקה, אבל שווה בדיקה כי " + "; ".join(signals[:3]) + "."
    elif _has_biomedical_review_signal(text):
        category, reason = (
            "review",
            "פחות מתאימה, אבל שווה בדיקה כי היא בתחום biomedical/medical device ויש בה נקודת חיבור מקצועית לפרופיל של מורן."
        )
    else:
        return "skip", "לא נמצאו מספיק סימנים שמחברים את המשרה לפרופיל של מורן."

    # Veto from the requirement-fit module: master degree (hard skip), degree
    # mismatch, or years required well above Moran's 2-year baseline.
    from requirement_fit import evaluate_fit
    veto = evaluate_fit(clean_requirements or job.requirements or job.description or "")
    if veto.requires_master:
        return "skip", veto.reason
    if veto.fit_category == "no_fit":
        return "skip", veto.reason
    if veto.fit_category == "review" and category == "fit":
        return "review", f"{veto.reason}. " + reason
    return category, reason


def _parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _applied_links_from_rtdb() -> set[str]:
    applied = rtdb_get("applied")
    if not isinstance(applied, dict):
        return set()
    links: set[str] = set()
    for item in applied.values():
        if isinstance(item, dict) and item.get("link"):
            links.add(str(item["link"]))
    return links


def should_publish_job(job: StoredJob, applied_links: set[str]) -> bool:
    """Keep applied jobs, but hide non-applied jobs after the retention window."""
    if job.link in applied_links:
        return True
    first_seen = _parse_iso_datetime(job.first_seen_at)
    if first_seen is None:
        return True
    if first_seen.tzinfo is None:
        first_seen = first_seen.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - first_seen <= timedelta(days=JOB_RETENTION_DAYS)


def job_record_id(link: str) -> str:
    return hashlib.sha1(link.strip().encode("utf-8")).hexdigest()


def _stored_job_from_record(record: dict) -> StoredJob:
    return StoredJob(
        title=str(record.get("title", "")),
        company=str(record.get("company", "")),
        location=str(record.get("location", "")),
        link=str(record.get("link", "")),
        source=str(record.get("source", "")),
        description=str(record.get("description", "")),
        is_relevant=bool(record.get("is_relevant", False)),
        matched_terms=str(record.get("matched_terms", "")),
        first_seen_at=str(record.get("first_seen_at", "")),
        last_seen_at=str(record.get("last_seen_at", "")),
        alive_status=str(record.get("alive_status", "")),
        alive_checked_at=str(record.get("alive_checked_at", "")),
        is_hot=bool(record.get("is_hot", False)),
        hot_terms=str(record.get("hot_terms", "")),
        requirements=str(record.get("requirements", "")),
        is_new=bool(record.get("is_new", False)),
    )


def _public_job_payload(job: StoredJob, fit_category: str, fit_reason: str) -> dict:
    from requirement_fit import evaluate_fit
    detail_text = job.requirements or job.description or ""
    summary_sections = parse_job_summary(detail_text).to_dict()
    fit_details = evaluate_fit(detail_text)
    searchable = " ".join([job.title, job.company, detail_text]).lower()
    is_biomedical = any(
        term in searchable for term in HOT_PROFILE_SIGNALS["medical_domain"]
    )
    payload = {
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "link": job.link,
        "source": job.source,
        "description": job.description,
        "matched_terms": job.matched_terms,
        "alive_status": job.alive_status,
        "is_hot": job.is_hot and fit_category == "fit",
        "is_biomedical": is_biomedical,
        "hot_terms": job.hot_terms,
        "requirements": detail_text,
        "summary_sections": summary_sections,
        "fit_category": fit_category,
        "fit_reason": fit_reason,
        "years_required": fit_details.years_required,
        "degree_fields": fit_details.degree_fields,
        "is_new": job.is_new,
        "first_seen_at": job.first_seen_at,
        "last_seen_at": job.last_seen_at,
    }
    ai_fit = assess_job_with_gemini(payload)
    if ai_fit is not None:
        payload["ai_fit_category"] = ai_fit.fit_category
        payload["ai_fit_confidence"] = ai_fit.confidence
        payload["ai_fit_reason"] = ai_fit.reason
        payload["ai_fit_source"] = ai_fit.source
        if ai_fit.fit_category == "skip":
            payload["fit_category"] = "review"
            payload["fit_reason"] = "Gemini ממליץ לדלג: " + ai_fit.reason
        elif ai_fit.fit_category == "fit" and fit_category == "review":
            payload["fit_category"] = "fit"
            payload["fit_reason"] = "Gemini מחזק התאמה: " + ai_fit.reason
    return payload


# ---------------------------------------------------------------------------
# Direct web scraping — fetch & parse raw HTML straight from the job boards
# ---------------------------------------------------------------------------

def _fetch_html(url: str, referer: str, timeout: int, retries: int = 3) -> str | None:
    """GET a URL with rotating browser headers and simple retry/backoff."""
    for attempt in range(retries + 1):
        try:
            resp = requests.get(
                url, headers=_random_headers(referer), timeout=timeout
            )
            if resp.status_code == 200:
                return resp.text
            if resp.status_code in (429, 403, 999):
                # Rate-limited / soft-blocked: exponential back-off with new headers.
                wait = REQUEST_DELAY_S * (2 ** (attempt + 1))
                logging.debug("HTTP %d for %s — waiting %.1fs", resp.status_code, url, wait)
                time.sleep(wait)
                continue
            if resp.status_code in (404, 410):
                return None  # Permanent — don't retry
            return None
        except requests.RequestException as exc:
            logging.debug("Request error for %s: %s", url, exc)
            time.sleep(REQUEST_DELAY_S * (attempt + 1))
    return None


def _is_job_posting_url(url: str) -> bool:
    """Keep only URLs that point at an individual posting, not a board index."""
    lower = url.lower()
    posting_markers = [
        "greenhouse.io/",     # boards.greenhouse.io/<co>/jobs/<id>
        "jobs.lever.co/",     # jobs.lever.co/<co>/<uuid>
        "comeet.com/jobs/",   # comeet.com/jobs/<co>/.../<id>
        "myworkdayjobs.com/", # <co>.wdN.myworkdayjobs.com/.../job/...
        "linkedin.com/jobs/view/",
    ]
    if not any(m in lower for m in posting_markers):
        return False
    if "greenhouse.io/" in lower and "/jobs/" not in lower:
        return False
    return True


# ---------------------------------------------------------------------------
# AllJobs.co.il — Israel's largest job board
# ---------------------------------------------------------------------------

# Hebrew-first keywords targeting Moran's profile on Israeli jobs
ALLJOBS_KEYWORDS = [
    "מהנדס ביו רפואי",
    "מהנדסת ביו רפואית",
    "מכשור רפואי",
    "הנדסה ביו רפואית",
    "מהנדס ולידציה",
    "מהנדסת ולידציה",
    "מהנדס פיתוח",
    "מהנדסת פיתוח",
    "מהנדס מכונות",
    "מהנדסת מכונות",
    "מהנדס תהליך",
    "מהנדסת תהליך",
    "biomedical engineer",
    "medical device engineer",
    "validation engineer",
    "cell culture engineer",
    "bioreactor engineer",
    "r&d engineer medical",
    "junior engineer biomedical",
]


def _parse_alljobs(html: str, source_url: str) -> list[Job]:
    """Extract job postings from an AllJobs.co.il search results page."""
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[Job] = []
    seen_links: set[str] = set()

    # AllJobs job-detail links contain JobID query param or /SeoJobSingle
    link_candidates = soup.select(
        "a[href*='JobID='], a[href*='SeoJobSingle'], a[href*='/jobs/view/']"
    )
    for link_el in link_candidates:
        href = link_el.get("href", "")
        if not href:
            continue
        link = urljoin("https://www.alljobs.co.il", href)
        if link in seen_links:
            continue
        seen_links.add(link)

        # Title: link text or nearest heading
        title = _clean(link_el.get_text(" "))
        parent_card = link_el.find_parent(["div", "li", "article", "tr"]) or link_el.parent
        if not title or len(title) < 5:
            if parent_card:
                heading = parent_card.select_one(
                    "h2, h3, h4, [class*='title'], [class*='position'], [class*='job-name']"
                )
                if heading:
                    title = _clean(heading.get_text(" "))
        if not title or not _looks_like_job_title(title):
            continue

        company = "Unknown"
        location = "Israel"
        if parent_card:
            co_el = parent_card.select_one(
                "[class*='company'], [class*='employer'], [class*='workplace'], [class*='מעסיק']"
            )
            loc_el = parent_card.select_one(
                "[class*='location'], [class*='city'], [class*='area'], [class*='עיר']"
            )
            if co_el:
                company = _clean(co_el.get_text(" ")) or "Unknown"
            if loc_el:
                location = _clean(loc_el.get_text(" ")) or "Israel"

        description = title
        if parent_card:
            desc_text = _clean(parent_card.get_text(" "))
            if len(desc_text) > len(title):
                description = desc_text[:700]

        jobs.append(Job(
            title=title,
            company=company,
            location=location,
            link=link,
            source="AllJobs",
            description=description,
        ))
    return jobs


def search_alljobs(config: Config) -> list[Job]:
    """Scrape AllJobs.co.il — Israel's largest job board (Hebrew + English)."""
    jobs: list[Job] = []
    for keyword in ALLJOBS_KEYWORDS:
        url = (
            "https://www.alljobs.co.il/SearchResultsGuest.aspx"
            f"?Query={quote_plus(keyword)}&Position=1"
        )
        html = _fetch_html(url, "https://www.alljobs.co.il/", config.request_timeout_seconds)
        if not html:
            time.sleep(REQUEST_DELAY_S)
            continue
        page_jobs = _parse_alljobs(html, url)
        jobs.extend(page_jobs)
        if page_jobs:
            logging.info("AllJobs '%s' → %d postings", keyword, len(page_jobs))
        time.sleep(REQUEST_DELAY_S)
    return jobs


def scrape_all(config: Config) -> list[Job]:
    """Run every direct-scrape source and return de-duplicated jobs."""
    jobs: list[Job] = []
    jobs.extend(search_linkedin(config))
    jobs.extend(search_greenhouse(config))
    jobs.extend(search_career_pages(config))
    jobs.extend(search_dynamic_boards(config))
    jobs.extend(search_alljobs(config))
    PASS_THROUGH_SOURCES = {"Career Page", "AllJobs"}
    jobs = [j for j in jobs if j.source in PASS_THROUGH_SOURCES or _is_job_posting_url(j.link)]
    unique = _dedupe(jobs)
    logging.info("Scraped %d raw / %d unique postings.", len(jobs), len(unique))
    return unique


# Kept as an alias so existing callers/tests keep working.
def search_duckduckgo(config: Config) -> list[Job]:  # noqa: D401 (legacy name)
    return scrape_all(config)


def search_linkedin(config: Config) -> list[Job]:
    """Scrape LinkedIn's public guest job search (Israel, last month)."""
    jobs: list[Job] = []
    for keyword in LINKEDIN_KEYWORDS:
        for page in range(LINKEDIN_PAGES):
            url = (
                f"{LINKEDIN_GUEST_URL}?keywords={quote_plus(keyword)}"
                f"&location=Israel&f_TPR={LINKEDIN_PAST_MONTH}&start={page * 25}"
            )
            html = _fetch_html(
                url, "https://www.linkedin.com/jobs", config.request_timeout_seconds
            )
            if not html:
                break  # blocked or no more pages for this keyword
            page_jobs = _parse_linkedin(html)
            jobs.extend(page_jobs)
            if len(page_jobs) < 5:
                break  # last page reached
            time.sleep(REQUEST_DELAY_S)
        logging.info("LinkedIn '%s' → running total %d", keyword, len(jobs))
    return jobs


def _parse_linkedin(html: str) -> list[Job]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[Job] = []
    for card in soup.select("li"):
        title_el = card.select_one("h3.base-search-card__title, h3")
        link_el = card.select_one("a.base-card__full-link, a[href*='/jobs/view/']")
        if not title_el or not link_el:
            continue
        company_el = card.select_one(
            "h4.base-search-card__subtitle a, h4.base-search-card__subtitle, h4"
        )
        location_el = card.select_one(".job-search-card__location")
        # Try to get a snippet/description from card metadata or benefit tags
        snippet_el = card.select_one(
            ".base-search-card__snippet, .job-search-card__snippet, "
            ".job-search-card__benefits-list, .base-search-card__metadata"
        )
        link = link_el.get("href", "").split("?")[0]
        if not link:
            continue
        title_text = _clean(title_el.get_text(" "))
        company_text = _clean(company_el.get_text(" ")) if company_el else "Unknown"
        snippet_text = _clean(snippet_el.get_text(" ")) if snippet_el else ""
        # Build description from title + company + snippet so keyword matching has more signal
        description = " | ".join(filter(None, [title_text, company_text, snippet_text]))
        jobs.append(Job(
            title=title_text,
            company=company_text,
            location=_clean(location_el.get_text(" ")) if location_el else "Israel",
            link=link,
            source="LinkedIn",
            description=description,
        ))
    return jobs


def search_greenhouse(config: Config) -> list[Job]:
    """Fetch jobs from the structured Greenhouse public JSON API per company.

    Endpoint: https://boards-api.greenhouse.io/v1/boards/{token}/jobs
    Filtered to Israel locations and the last month (updated_at).
    """
    cutoff = datetime.now(timezone.utc).timestamp() - 31 * 86400
    jobs: list[Job] = []
    for company in GREENHOUSE_COMPANIES:
        url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs"
        try:
            resp = requests.get(
                url, headers=_random_headers(), timeout=config.request_timeout_seconds
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
        except (requests.RequestException, ValueError):
            continue

        company_jobs = []
        for item in data.get("jobs", []):
            location = (item.get("location") or {}).get("name", "")
            if not _in_israel(location):
                continue
            if not _within_cutoff(item.get("updated_at", ""), cutoff):
                continue
            company_jobs.append(Job(
                title=_clean(item.get("title", "Untitled")),
                company=company.title(),
                location=_clean(location) or "Israel",
                link=item.get("absolute_url", ""),
                source="Greenhouse",
                description=_clean(item.get("title", "")),
            ))
        jobs.extend(company_jobs)
        if company_jobs:
            logging.info("Greenhouse '%s' → %d Israel postings", company, len(company_jobs))
        time.sleep(REQUEST_DELAY_S)
    return jobs


def search_career_pages(config: Config) -> list[Job]:
    """Scrape curated biomedical/medical-device company career pages.

    These pages often contain high-quality roles that do not appear reliably in
    LinkedIn guest search. We keep this source curated to avoid broad noisy web
    crawling.
    """
    jobs: list[Job] = []
    for page in CAREER_PAGES:
        url = page["url"]
        html = _fetch_html(url, url, config.request_timeout_seconds)
        if not html:
            continue
        page_jobs = _parse_career_page(
            html,
            company=page["company"],
            url=url,
            domain=page.get("domain", ""),
        )
        jobs.extend(page_jobs)
        if page_jobs:
            logging.info("Career page '%s' → %d postings", page["company"], len(page_jobs))
        time.sleep(REQUEST_DELAY_S)
    return jobs


def _parse_career_page(html: str, company: str, url: str, domain: str = "") -> list[Job]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    jobs: list[Job] = []
    seen_titles: set[str] = set()
    heading_selectors = "h1, h2, h3, h4, a"
    for node in soup.select(heading_selectors):
        title = _clean(node.get_text(" "))
        if not _looks_like_job_title(title):
            continue
        title_key = title.lower()
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        block = _career_context_text(node)
        if not block:
            block = title
        if domain:
            block = f"{domain}\n{block}"
        href = node.get("href") if node.name == "a" else ""
        link = urljoin(url, href) if href else f"{url}#{quote_plus(title[:60])}"
        jobs.append(Job(
            title=title,
            company=company,
            location=_infer_location(block) or "Israel",
            link=link.split("?")[0],
            source="Career Page",
            description=_clean(block)[:1200],
        ))
    return jobs


def _looks_like_job_title(text: str) -> bool:
    if not text or len(text) < 6 or len(text) > 120:
        return False
    low = text.lower()
    exact_skip = {
        "quality assurance", "engineering & validation", "engineering and validation",
        "medical devices", "set up your qst lab", "setting up your qst lab",
    }
    if low in exact_skip:
        return False
    if any(skip in low for skip in [
        "apply", "careers", "open positions", "join us", "privacy", "terms",
        "contact", "newsletter", "send us", "home", "about",
    ]):
        return False
    title_terms = [
        "engineer", "technician", "operator", "specialist", "associate",
        "validation", "quality", "regulatory", "process", "production",
        "mechanical", "biomedical", "medical device", "r&d", "lab",
        "scientist", "researcher", "biologist", "analyst", "developer",
        "cell culture", "bioprocess", "bioreactor", "upstream", "downstream",
        "מהנדס", "מהנדסת", "טכנאי", "טכנאית", "איכות", "ולידציה",
        "ייצור", "תהליך", "מעבדה", "חוקר", "חוקרת", "מדען", "מדענית",
    ]
    return any(term in low for term in title_terms)


def _career_context_text(node) -> str:
    parts: list[str] = []
    title = _clean(node.get_text(" "))
    if title:
        parts.append(title)

    for sib in node.find_all_next(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li"], limit=16):
        if sib is node:
            continue
        if sib.name in {"h1", "h2", "h3", "h4"} and _looks_like_next_career_heading(_clean(sib.get_text(" "))):
            break
        text = _clean(sib.get_text(" "))
        if text and text not in parts:
            parts.append(text)
        if len(parts) >= 10:
            break

    if len(parts) < 3:
        parent = node.find_parent(["article", "section", "li"]) or node.parent
        if parent:
            for sib in parent.find_all(["p", "li", "h5", "h6"], limit=10):
                text = _clean(sib.get_text(" "))
                if text and text not in parts:
                    parts.append(text)
    return "\n".join(parts[:12])


def _looks_like_next_career_heading(text: str) -> bool:
    if not text or len(text) > 140:
        return False
    low = text.lower()
    heading_terms = [
        "engineer", "manager", "specialist", "representative", "coordinator",
        "employee", "operator", "technician", "associate", "project",
        "מהנדס", "מהנדסת", "מנהל", "מנהלת", "רכז", "טכנאי", "טכנאית",
    ]
    return any(term in low for term in heading_terms)


def _in_israel(location: str) -> bool:
    low = location.lower()
    return any(loc in low for loc in LOCATIONS) or "israel" in low or not location


def _within_cutoff(iso_ts: str, cutoff_epoch: float) -> bool:
    """True if an ISO8601 timestamp is newer than the cutoff (or unparseable)."""
    if not iso_ts:
        return True
    try:
        ts = datetime.fromisoformat(iso_ts.replace("Z", "+00:00")).timestamp()
        return ts >= cutoff_epoch
    except ValueError:
        return True


def _parse_greenhouse(html: str, company: str) -> list[Job]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[Job] = []
    for link_el in soup.select("a[href*='/jobs/']"):
        href = link_el.get("href", "")
        if "/jobs/" not in href:
            continue
        link = href if href.startswith("http") else urljoin(
            "https://job-boards.greenhouse.io", href
        )
        raw = link_el.get_text(" ", strip=True)
        # Greenhouse concatenates "<Title><Location>"; split on the location.
        location = ""
        title = raw
        cell = link_el.find_parent(["tr", "div"])
        if cell:
            loc_el = cell.select_one(".location, td.cell-location, .job-location")
            if loc_el:
                location = _clean(loc_el.get_text(" "))
                title = _clean(raw.replace(location, ""))
        jobs.append(Job(
            title=_clean(title) or raw,
            company=company.title(),
            location=location or _infer_location(raw),
            link=link.split("?")[0],
            source="Greenhouse",
            description=raw,
        ))
    return jobs


def search_dynamic_boards(config: Config) -> list[Job]:
    """Render JS-heavy boards (Comeet/Workday) via Playwright if available."""
    if not DYNAMIC_BOARDS:
        return []
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        logging.info("Playwright not installed; skipping dynamic boards.")
        return []

    jobs: list[Job] = []
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for url in DYNAMIC_BOARDS:
            try:
                pg = browser.new_page(user_agent=random.choice(USER_AGENTS))
                pg.goto(url, timeout=config.request_timeout_seconds * 1000)
                pg.wait_for_timeout(2500)
                jobs.extend(_parse_greenhouse(pg.content(), url))
                pg.close()
            except Exception as exc:
                logging.error("Dynamic board %s failed: %s", url, exc)
        browser.close()
    return jobs


# ---------------------------------------------------------------------------
# Liveness verification — confirm each posting is still live on the ATS
# ---------------------------------------------------------------------------

# Phrases that appear on an ATS page after a posting is closed/removed.
DEAD_MARKERS = [
    "no longer available", "no longer accepting", "no longer open",
    "position has been filled", "position has been closed", "job is closed",
    "this job is no longer", "posting is not available", "posting isn't available",
    "couldn't find that page", "page not found", "404 not found",
    "the job you are looking for", "job not found", "this position is closed",
    "applications are no longer", "we are no longer accepting",
    "המשרה אינה", "המשרה הוסרה", "משרה לא נמצאה", "המשרה נסגרה",
    "כבר לא מקבלים בקשות", "לא מקבלים בקשות",
]

ALIVE = "alive"
DEAD = "dead"
UNKNOWN = "unknown"


def _classify_alive(link: str, status_code: int, final_url: str, text: str) -> str:
    """Decide liveness from an HTTP response."""
    if status_code in (404, 410):
        return DEAD
    if status_code in (403, 429, 999):
        return UNKNOWN  # blocked / rate-limited, can't conclude
    if status_code >= 400:
        return UNKNOWN
    link_l, final_l, text_l = link.lower(), final_url.lower(), text.lower()
    # Greenhouse redirects a removed posting back to the board root.
    if "greenhouse.io/" in link_l and "/jobs/" not in final_l:
        return DEAD
    # LinkedIn bounces an expired/removed job to a login/authwall page.
    if "linkedin.com/jobs/view/" in link_l and "/jobs/view/" not in final_l:
        return DEAD
    if any(marker in text_l for marker in DEAD_MARKERS):
        return DEAD
    return ALIVE


@dataclass(frozen=True)
class Inspection:
    status: str
    is_hot: bool
    hot_terms: list[str]
    requirements: str = ""


def check_job_alive(link: str, timeout: int = 15) -> str:
    """Fetch the posting URL and decide whether it is still live.

    Returns 'alive', 'dead', or 'unknown' (network/anti-bot — kept, not dropped).
    """
    return inspect_job(link, timeout).status


def _extract_requirements(html: str, is_linkedin: bool, link: str = "") -> str:
    """Pull the readable job-description / requirements text out of a page."""
    soup = BeautifulSoup(html, "html.parser")
    if is_linkedin:
        node = soup.select_one(
            ".show-more-less-html__markup, .description__text, .core-section-container__content"
        )
        text = node.get_text("\n") if node else soup.get_text("\n")
    elif "#" in link:
        title_hint = unquote_plus(link.rsplit("#", 1)[1]).strip()
        node = _find_heading_by_text(soup, title_hint)
        text = _career_context_text(node) if node else ""
        if not text:
            node = soup.select_one(
                "#content, .content, #app_body, .opening, main, article"
            )
            text = node.get_text("\n") if node else soup.get_text("\n")
    else:
        node = soup.select_one(
            "#content, .content, #app_body, .opening, main, article"
        )
        text = node.get_text("\n") if node else soup.get_text("\n")
    # Normalize whitespace but keep line breaks for readability.
    lines = [ln.strip() for ln in text.splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    return text[:6000]


def _find_heading_by_text(soup: BeautifulSoup, title_hint: str):
    if not title_hint:
        return None
    wanted = _clean(title_hint).lower()
    for node in soup.select("h1, h2, h3, h4, a"):
        text = _clean(node.get_text(" "))
        if text and (text.lower() == wanted or text.lower().startswith(wanted[:40])):
            return node
    return None


def inspect_job(link: str, timeout: int = 15) -> Inspection:
    """Visit a posting once → liveness + 'hot' match + full requirements text.

    LinkedIn blocks rapid GETs to /jobs/view/ pages (HTTP 999); its public
    per-job guest endpoint serves the full description, so we use it for all
    three signals at once.
    """
    is_linkedin = "linkedin.com/jobs/view/" in link.lower()
    if is_linkedin:
        match = re.search(r"(\d{6,})(?:\D*)$", link)
        if not match:
            return Inspection(UNKNOWN, False, [])
        target = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/" + match.group(1)
        allow_redirects = True
    else:
        target = link
        allow_redirects = True

    resp = None
    # LinkedIn throttles bursts with HTTP 999; retry a couple of times so a
    # transient block doesn't mask a live (and possibly "hot") posting.
    for attempt in range(3):
        try:
            resp = requests.get(
                target, headers=_random_headers(), timeout=timeout,
                allow_redirects=allow_redirects,
            )
        except requests.RequestException:
            return Inspection(UNKNOWN, False, [])
        if resp.status_code not in (999, 429):
            break
        time.sleep(1.5 * (attempt + 1) + random.random())

    if resp is None:
        return Inspection(UNKNOWN, False, [])
    if is_linkedin:
        status = _classify_linkedin(resp.status_code, resp.text)
    else:
        status = _classify_alive(link, resp.status_code, str(resp.url), resp.text)
    if resp.status_code == 200:
        is_hot, terms = evaluate_hotness(resp.text)
        requirements = _extract_requirements(resp.text, is_linkedin, link)
        return Inspection(status, is_hot, terms, requirements)
    return Inspection(status, False, [])


def _classify_linkedin(status_code: int, text: str) -> str:
    """Liveness for LinkedIn's guest jobPosting endpoint (its URL never contains
    /jobs/view/, so the generic redirect heuristic must not apply here)."""
    if status_code in (404, 410):
        return DEAD
    if status_code in (403, 429, 999):
        return UNKNOWN
    if status_code >= 400:
        return UNKNOWN
    if any(marker in text.lower() for marker in DEAD_MARKERS):
        return DEAD
    return ALIVE


def verify_jobs_alive(links: list[str], max_workers: int = 2) -> dict[str, str]:
    """Concurrently check liveness for many links. Returns {link: status}."""
    return {link: ins.status for link, ins in inspect_jobs(links, max_workers).items()}


def inspect_jobs(links: list[str], max_workers: int = 2) -> dict[str, Inspection]:
    """Concurrently inspect links → {link: Inspection}."""
    results: dict[str, Inspection] = {}
    if not links:
        return results
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for link, ins in zip(links, pool.map(inspect_job, links)):
            results[link] = ins
    alive = sum(1 for i in results.values() if i.status == ALIVE)
    dead = sum(1 for i in results.values() if i.status == DEAD)
    unknown = sum(1 for i in results.values() if i.status == UNKNOWN)
    hot = sum(1 for i in results.values() if i.is_hot)
    logging.info(
        "Inspection: %d alive, %d dead, %d unknown, %d HOT (of %d).",
        alive, dead, unknown, hot, len(results),
    )
    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean(value: str) -> str:
    return " ".join(value.split()).strip()


def _infer_company(link: str) -> str:
    lower = link.lower()
    for marker in [
        "boards.greenhouse.io/",
        "jobs.lever.co/",
        "comeet.com/jobs/",
        "comeet.com/careers/",
    ]:
        if marker in lower:
            slug = link.split(marker, 1)[1].split("/", 1)[0]
            return _clean(slug.replace("-", " ").replace("_", " ")).title()
    if "myworkdayjobs.com" in lower:
        # e.g. https://acme.wd1.myworkdayjobs.com/...  → "Acme"
        host = link.split("//", 1)[-1].split("/", 1)[0]
        return _clean(host.split(".", 1)[0].replace("-", " ")).title()
    if "linkedin.com" in lower:
        return "LinkedIn"
    return "Unknown"


def _infer_location(text: str) -> str:
    lower = text.lower()
    for loc in LOCATIONS:
        if loc in lower:
            return loc.title()
    return "Israel"


def _dedupe(jobs: list[Job]) -> list[Job]:
    seen: set[str] = set()
    unique: list[Job] = []
    for job in jobs:
        key = job.link.strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(job)
    return unique


def dedupe_jobs_in_memory(jobs: Iterable[Job]) -> list[Job]:
    return _dedupe(list(jobs))


class SeenStore:
    """Lightweight JSON-backed dedup store (jobs_seen.json), per spec.

    Hashes each job link so a posting is only processed/notified once.
    """

    def __init__(self, path: str = SEEN_JSON_PATH) -> None:
        self.path = path
        self._seen: set[str] = set()
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    self._seen = set(json.load(fh))
            except (json.JSONDecodeError, OSError):
                self._seen = set()

    @staticmethod
    def _key(link: str) -> str:
        return hashlib.sha1(link.strip().encode("utf-8")).hexdigest()

    def has_seen(self, link: str) -> bool:
        return self._key(link) in self._seen

    def mark_seen(self, link: str) -> None:
        self._seen.add(self._key(link))

    def save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(sorted(self._seen), fh)


def infer_company_from_link(link: str) -> str:
    return _infer_company(link)


def absolute_url(base_url: str, maybe_relative_url: str) -> str:
    return urljoin(base_url, maybe_relative_url)


ProcessedJobStore = JobStore


# ---------------------------------------------------------------------------
# Google Sheets export (optional)
# ---------------------------------------------------------------------------

def append_to_sheet(config: Config, job: Job) -> None:
    if config.dry_run:
        logging.info("[dry-run] Would append to Sheets: %s", job.link)
        return
    if not config.sheets_enabled:
        return
    try:
        client = _get_sheets_client(config)
        ws = client.open_by_key(config.google_sheet_id).worksheet(config.google_sheet_name)
        ws.append_row(
            [datetime.now().strftime("%Y-%m-%d"), job.title, job.company, job.location, job.link],
            value_input_option="USER_ENTERED",
        )
    except Exception as exc:
        logging.exception("Sheets append failed: %s", exc)


def _get_sheets_client(config: Config):
    if gspread is None or Credentials is None:
        raise RuntimeError("Install gspread and google-auth to enable Google Sheets.")
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    if config.google_service_account_json:
        creds = Credentials.from_service_account_info(
            json.loads(config.google_service_account_json), scopes=scopes
        )
    elif config.google_service_account_file:
        creds = Credentials.from_service_account_file(
            config.google_service_account_file, scopes=scopes
        )
    else:
        raise RuntimeError(
            "SHEETS_ENABLED=true requires GOOGLE_SERVICE_ACCOUNT_FILE or GOOGLE_SERVICE_ACCOUNT_JSON."
        )
    return gspread.authorize(creds)


# ---------------------------------------------------------------------------
# Sample data for offline testing
# ---------------------------------------------------------------------------

def sample_jobs() -> list[Job]:
    return [
        Job(
            title="Junior R&D Mechanical Engineer",
            company="MedTech IL",
            location="Rehovot, Israel",
            link="https://boards.greenhouse.io/medtechil/jobs/001",
            source="Sample",
            description="SolidWorks, CAD, 3D printing, MATLAB, bioreactors. Rehovot.",
        ),
        Job(
            title="Lab Technician – Food Bioprocessing",
            company="FoodTech Startup",
            location="Tel Aviv",
            link="https://jobs.lever.co/foodtech/jobs/002",
            source="Sample",
            description="Bioreactors, cell culture, food tech, Tel Aviv Israel.",
        ),
        Job(
            title="Senior Finance Manager",
            company="Big Bank",
            location="London",
            link="https://example.com/jobs/senior-finance",
            source="Sample",
            description="Senior-level budgeting and reporting.",
        ),
    ]


# ---------------------------------------------------------------------------
# Processing pipeline
# ---------------------------------------------------------------------------

def process_jobs(
    config: Config,
    store: JobStore,
    jobs: list[Job],
    seen: "SeenStore | None" = None,
) -> int:
    """Filter, store, and count newly found relevant jobs.

    Dedup uses the JSON SeenStore when provided (jobs_seen.json); otherwise it
    falls back to the SQLite seen table.
    """
    new_count = 0
    for job in jobs:
        store.upsert_job(job)

        is_seen = seen.has_seen(job.link) if seen is not None else store.has_seen(job.link)
        if is_seen:
            logging.debug("Already processed: %s", job.link)
            continue

        if not is_relevant_job(job):
            if seen is not None:
                seen.mark_seen(job.link)
            else:
                store.mark_seen(job)
            continue

        _print_job(job)
        append_to_sheet(config, job)
        if seen is not None:
            seen.mark_seen(job.link)
        else:
            store.mark_seen(job)
        new_count += 1

    if seen is not None:
        seen.save()
    return new_count


def _print_job(job: Job) -> None:
    terms = ", ".join(find_matched_terms(job))
    print("\n" + "-" * 64)
    print(f"  Title:    {job.title}")
    print(f"  Company:  {job.company}")
    print(f"  Location: {job.location}")
    print(f"  Match:    {terms}")
    print(f"  Link:     {job.link}")
    if job.description:
        print(f"  Snippet:  {job.description[:200]}")
    print("-" * 64)


def run_scan(
    config: Config, use_sample: bool = False, verify: bool = True
) -> tuple[int, int]:
    store = JobStore(config.sqlite_path)
    seen = SeenStore(SEEN_JSON_PATH)
    known_before = store.existing_links()
    raw = sample_jobs() if use_sample else scrape_all(config)
    jobs = _dedupe(raw)
    new_relevant = process_jobs(config, store, jobs, seen=seen)

    # Flag postings first discovered in this scan as "new" for the dashboard.
    new_links = {j.link for j in jobs if j.link not in known_before}
    store.set_new_flags(new_links)
    logging.info("%d new postings since last scan.", len(new_links))

    if verify and not use_sample:
        verify_existing(store, config)

    return len(jobs), new_relevant


def verify_existing(store: JobStore, config: Config) -> dict[str, str]:
    """Visit every relevant posting: record liveness AND 'hot' (B.Sc. Medical
    Engineering requirement) from the same page fetch."""
    links = store.relevant_links()
    logging.info("Inspecting %d relevant postings (liveness + hot + requirements)...", len(links))
    outcomes = inspect_jobs(links)
    statuses: dict[str, str] = {}
    for link, ins in outcomes.items():
        store.update_inspection(
            link, ins.status, ins.is_hot,
            ", ".join(sorted(set(ins.hot_terms))), ins.requirements,
        )
        statuses[link] = ins.status
    return statuses


def build_public_jobs_from_state(
    state: dict[str, dict],
    applied_links: set[str],
) -> list[dict]:
    jobs: list[dict] = []
    for record in state.values():
        if not isinstance(record, dict):
            continue
        stored = _stored_job_from_record(record)
        if not stored.link or stored.alive_status == DEAD:
            continue
        if not should_publish_job(stored, applied_links):
            continue
        fit_category, fit_reason = analyze_moran_fit(stored)
        if fit_category == "skip":
            continue
        jobs.append(_public_job_payload(stored, fit_category, fit_reason))
    return sorted(
        jobs,
        key=lambda j: (
            not bool(j.get("is_new")),
            j.get("fit_category") != "fit",
            not bool(j.get("is_hot")),
            not bool(j.get("is_biomedical")),
            str(j.get("last_seen_at", "")),
        ),
    )


def run_cloud_scan(config: Config, use_sample: bool = False) -> dict[str, int]:
    """Run the full scraper with Firebase RTDB as the durable system of record."""
    now = datetime.now(timezone.utc).isoformat()
    existing_raw = rtdb_get("job_state")
    existing_state: dict[str, dict] = existing_raw if isinstance(existing_raw, dict) else {}
    applied_links = _applied_links_from_rtdb()

    raw_jobs = sample_jobs() if use_sample else scrape_all(config)
    scraped_jobs = [job for job in _dedupe(raw_jobs) if is_relevant_job(job)]
    scraped_ids = {job_record_id(job.link) for job in scraped_jobs}

    state: dict[str, dict] = {}
    for job_id, record in existing_state.items():
        if isinstance(record, dict):
            state[job_id] = {**record, "is_new": False}

    new_relevant = 0
    for job in scraped_jobs:
        job_id = job_record_id(job.link)
        existing = state.get(job_id, {})
        if not existing:
            new_relevant += 1
        first_seen_at = str(existing.get("first_seen_at") or now)
        state[job_id] = {
            **existing,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "link": job.link,
            "source": job.source,
            "description": job.description,
            "is_relevant": True,
            "matched_terms": ", ".join(find_matched_terms(job)),
            "first_seen_at": first_seen_at,
            "last_seen_at": now,
            "is_new": not bool(existing),
        }

    inspections = inspect_jobs([job.link for job in scraped_jobs])
    for job in scraped_jobs:
        job_id = job_record_id(job.link)
        record = state[job_id]
        inspection = inspections.get(job.link)
        if not inspection:
            continue
        record["alive_status"] = inspection.status
        record["alive_checked_at"] = now
        record["is_hot"] = inspection.is_hot
        record["hot_terms"] = ", ".join(sorted(set(inspection.hot_terms)))
        if inspection.requirements:
            record["requirements"] = inspection.requirements

    # Keep applied historical jobs, but hard-prune stale non-applied jobs from cloud state.
    pruned_state: dict[str, dict] = {}
    for job_id, record in state.items():
        stored = _stored_job_from_record(record)
        if job_id in scraped_ids or should_publish_job(stored, applied_links):
            pruned_state[job_id] = record

    public_jobs = build_public_jobs_from_state(pruned_state, applied_links)
    payload = {
        "generated_at": now,
        "count": len(public_jobs),
        "jobs": public_jobs,
    }
    rtdb_put("job_state", pruned_state)
    push_to_rtdb(payload)
    return {
        "scraped": len(scraped_jobs),
        "new_relevant": new_relevant,
        "published": len(public_jobs),
        "state": len(pruned_state),
    }


def export_jobs_json(sqlite_path: str, out_path: str = "public/jobs.json") -> int:
    """Export relevant, non-expired jobs to JSON for the Firebase dashboard."""
    store = JobStore(sqlite_path)
    applied_links = _applied_links_from_rtdb()
    jobs = []
    for j in store.list_jobs():
        if j.alive_status == "dead":
            continue
        if not should_publish_job(j, applied_links):
            continue
        fit_category, fit_reason = analyze_moran_fit(j)
        if fit_category == "skip":
            continue
        jobs.append(_public_job_payload(j, fit_category, fit_reason))
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(jobs),
        "jobs": jobs,
    }
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    logging.info("Exported %d jobs to %s", len(jobs), out_path)
    push_to_rtdb(payload)
    return len(jobs)


def push_to_rtdb(payload: dict) -> bool:
    """Publish the jobs feed to Firebase Realtime Database."""
    jobs_ok = rtdb_put("jobs", payload["jobs"])
    meta_ok = rtdb_put(
        "meta",
        {"generated_at": payload["generated_at"], "count": payload["count"]},
    )
    if jobs_ok and meta_ok:
        logging.info("Pushed %d jobs to Realtime Database.", payload["count"])
        return True
    logging.warning("RTDB push incomplete. Check service account access and database rules.")
    return False


def _push_to_rtdb_legacy(payload: dict) -> bool:
    """Publish the jobs feed to Firebase Realtime Database so the live dashboard
    always reflects the latest scan without a re-deploy. Returns True on success.
    """
    params = _rtdb_params()
    try:
        # Write jobs + meta. (Leaves the /applied node — written by the dashboard.)
        resp = requests.put(
            f"{RTDB_URL}/jobs.json", params=params, json=payload["jobs"], timeout=30
        )
        requests.put(
            f"{RTDB_URL}/meta.json", params=params,
            json={"generated_at": payload["generated_at"], "count": payload["count"]},
            timeout=30,
        )
        if resp.status_code == 200:
            logging.info("Pushed %d jobs to Realtime Database.", payload["count"])
            return True
        logging.warning(
            "RTDB push failed (HTTP %s). Deploy database.rules.json to allow writes.",
            resp.status_code,
        )
    except requests.RequestException as exc:
        logging.warning("RTDB push error: %s", exc)
    return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Direct-scrape job search (LinkedIn + Greenhouse, last month, Israel)."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Run without writing to external services.")
    parser.add_argument("--sample", action="store_true",
                        help="Use built-in sample data instead of a live search.")
    parser.add_argument("--no-verify", action="store_true",
                        help="Skip the liveness check of postings.")
    parser.add_argument("--verify-only", action="store_true",
                        help="Only re-check liveness of jobs already in the database.")
    parser.add_argument("--export", nargs="?", const="public/jobs.json", default=None,
                        help="Export relevant live jobs to JSON for Firebase (default: public/jobs.json).")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    setup_logging()
    config = load_config()
    if args.dry_run:
        config = Config(**{**asdict(config), "dry_run": True})

    if args.verify_only:
        store = JobStore(config.sqlite_path)
        statuses = verify_existing(store, config)
        dead = sum(1 for s in statuses.values() if s == DEAD)
        logging.info("Done. Re-verified %d postings (%d now dead).", len(statuses), dead)
        if args.export is not None:
            export_jobs_json(config.sqlite_path, args.export)
        return

    found, new_relevant = run_scan(
        config, use_sample=args.sample, verify=not args.no_verify
    )
    store = JobStore(config.sqlite_path)
    live = store.count_live_relevant()
    hot = store.count_hot()
    logging.info(
        "Done. %d scanned, %d new relevant, %d live, %d HOT (B.Sc. Medical Eng).",
        found, new_relevant, live, hot,
    )
    # Always refresh the Firebase data feed after a live scan.
    out = args.export if args.export is not None else "public/jobs.json"
    export_jobs_json(config.sqlite_path, out)


if __name__ == "__main__":
    main()
