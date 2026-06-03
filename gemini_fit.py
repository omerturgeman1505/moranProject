"""Quota-conscious Gemini review for job fit.

Runs only after local filters already narrowed the list, caches by content
fingerprint, and enforces a local daily call cap for free-tier usage.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Iterator

import requests


DEFAULT_MODEL = "gemini-2.0-flash-lite"
DEFAULT_CACHE_PATH = "gemini_fit_cache.sqlite3"


@dataclass(frozen=True)
class GeminiFitResult:
    fit_category: str
    confidence: int
    reason: str
    source: str = "gemini"


def gemini_enabled() -> bool:
    return (
        os.getenv("GEMINI_ENABLED", "false").lower() == "true"
        and bool(os.getenv("GEMINI_API_KEY", "").strip())
    )


def _cache_path() -> str:
    return os.getenv("GEMINI_CACHE_PATH", DEFAULT_CACHE_PATH)


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(_cache_path())
    try:
        _init_db(conn)
        yield conn
    finally:
        conn.close()


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS gemini_fit_cache (
            fingerprint TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            model TEXT NOT NULL,
            fit_category TEXT NOT NULL,
            confidence INTEGER NOT NULL,
            reason TEXT NOT NULL,
            raw_json TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS gemini_usage (
            day TEXT PRIMARY KEY,
            calls INTEGER NOT NULL
        )
    """)
    conn.commit()


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _daily_limit() -> int:
    try:
        return max(0, int(os.getenv("GEMINI_DAILY_LIMIT", "20")))
    except ValueError:
        return 20


def _can_spend_call(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT calls FROM gemini_usage WHERE day = ?", (_today(),)
    ).fetchone()
    return (row[0] if row else 0) < _daily_limit()


def _mark_call(conn: sqlite3.Connection) -> None:
    conn.execute("""
        INSERT INTO gemini_usage(day, calls) VALUES(?, 1)
        ON CONFLICT(day) DO UPDATE SET calls = calls + 1
    """, (_today(),))
    conn.commit()


def _fingerprint(job_payload: dict) -> str:
    parts = [
        str(job_payload.get("title", "")),
        str(job_payload.get("company", "")),
        str(job_payload.get("location", "")),
        str(job_payload.get("requirements", "")),
        str(job_payload.get("description", "")),
    ]
    return hashlib.sha256("\n\n".join(parts).encode("utf-8")).hexdigest()


def _allowed_for_category(local_category: str) -> bool:
    raw = os.getenv("GEMINI_ON_CATEGORIES", "review").lower()
    allowed = {part.strip() for part in raw.split(",") if part.strip()}
    return local_category.lower() in allowed


def _prompt(job_payload: dict) -> str:
    max_chars = int(os.getenv("GEMINI_MAX_INPUT_CHARS", "6000"))
    requirements = str(job_payload.get("requirements") or job_payload.get("description") or "")
    requirements = requirements[:max_chars]
    profile = (
        "Candidate: Moran. B.Sc. Medical Engineering from Afeka Tel Aviv "
        "Academic College of Engineering, 2020-2024, majoring in physiologic "
        "system mechanics. Lab technician engineering R&D since 2024. Operates, "
        "maintains, assembles, and calibrates bioreactors; records and analyzes "
        "process data with DOT systems and Excel; supports process optimization "
        "and decision-making; collaborates on water-saving solutions for large "
        "scale cell culture. Experienced with FlexCell, TruBio, Cellaca, Twin, "
        "MFCS, Cedex BioAnalyzer, Masterflex, SolidWorks, Excel, Microsoft "
        "Office, MATLAB, and Python. Final project: new spiral IUD prototype "
        "and evaluation, including custom inserter/removal-device challenges "
        "using SolidWorks and 3D printing. Strong fit areas: medical devices, "
        "mechanical design/CAD/SolidWorks, R&D, lab work, bioreactors, cell "
        "culture, process optimization, validation, SOPs, data analysis. "
        "Avoid roles requiring Master's degree, clearly senior/lead/manager roles, "
        "or hard requirements above 3 years experience."
    )
    return (
        f"{profile}\n\n"
        "Classify this job for the candidate. Return strict JSON only with keys: "
        "fit_category ('fit'|'review'|'skip'), confidence (0-100), reason_he "
        "(short Hebrew explanation).\n\n"
        f"Title: {job_payload.get('title', '')}\n"
        f"Company: {job_payload.get('company', '')}\n"
        f"Location: {job_payload.get('location', '')}\n"
        f"Local fit: {job_payload.get('fit_category', '')} - {job_payload.get('fit_reason', '')}\n"
        f"Requirements:\n{requirements}"
    )


def _parse_response(data: dict) -> GeminiFitResult | None:
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        return None
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.removeprefix("json").strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        logging.warning("Gemini returned non-JSON fit response: %s", text[:200])
        return None
    category = str(parsed.get("fit_category", "")).lower()
    if category not in {"fit", "review", "skip"}:
        return None
    try:
        confidence = int(parsed.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0
    return GeminiFitResult(
        fit_category=category,
        confidence=max(0, min(100, confidence)),
        reason=str(parsed.get("reason_he", "")).strip()[:500],
    )


def assess_job_with_gemini(job_payload: dict) -> GeminiFitResult | None:
    """Return cached/new Gemini assessment, or None when disabled/over budget."""
    local_category = str(job_payload.get("fit_category", ""))
    if not gemini_enabled() or not _allowed_for_category(local_category):
        return None

    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    fingerprint = _fingerprint(job_payload)
    with _connect() as conn:
        row = conn.execute(
            "SELECT fit_category, confidence, reason FROM gemini_fit_cache WHERE fingerprint = ?",
            (fingerprint,),
        ).fetchone()
        if row:
            return GeminiFitResult(row[0], int(row[1]), row[2], source="gemini_cache")
        if not _can_spend_call(conn):
            logging.info("Gemini daily limit reached; using local fit only.")
            return None

        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )
        body = {
            "contents": [{"parts": [{"text": _prompt(job_payload)}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 220,
                "responseMimeType": "application/json",
            },
        }
        try:
            resp = requests.post(url, json=body, timeout=20)
            _mark_call(conn)
            if resp.status_code != 200:
                logging.warning("Gemini fit call failed (HTTP %s): %s", resp.status_code, resp.text[:200])
                return None
            result = _parse_response(resp.json())
        except requests.RequestException as exc:
            _mark_call(conn)
            logging.warning("Gemini fit call failed: %s", exc)
            return None
        if result is None:
            return None
        conn.execute(
            "INSERT OR REPLACE INTO gemini_fit_cache "
            "(fingerprint, created_at, model, fit_category, confidence, reason, raw_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                fingerprint,
                datetime.now(timezone.utc).isoformat(),
                model,
                result.fit_category,
                result.confidence,
                result.reason,
                json.dumps(asdict(result), ensure_ascii=False),
            ),
        )
        conn.commit()
        return result
