from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, redirect, render_template_string, request, url_for

from job_search_platform import (
    RTDB_URL,
    Config,
    JobStore,
    export_jobs_json,
    load_config,
    publish_scan_status,
    rtdb_put,
    run_scan,
    setup_logging,
)

app = Flask(__name__)
setup_logging()

# Shared scan state for the async "run scan" button.
_scan_lock = threading.Lock()
_scan_state = {"running": False, "message": "", "just_finished": False}


PAGE = """
<!doctype html>
<html lang="he" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>מערכת חיפוש משרות</title>
  <style>
    :root {
      --bg: #f6f7f9; --panel: #ffffff; --ink: #1f2937; --muted: #667085;
      --line: #d9dee7; --good: #0f766e; --bad: #9f1239; --accent: #2563eb;
      --chip: #eef2ff;
    }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: Arial, "Segoe UI", sans-serif; background: var(--bg); color: var(--ink); }
    header { background: #fff; border-bottom: 1px solid var(--line); padding: 22px 28px; }
    main { max-width: 1280px; margin: 0 auto; padding: 24px; }
    h1 { margin: 0 0 6px; font-size: 28px; }
    .subtitle { color: var(--muted); margin: 0; font-size: 14px; }
    .toolbar { display: grid; grid-template-columns: 1fr auto; gap: 16px; align-items: end; margin-bottom: 18px; }
    .stats { display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 12px; }
    .stat, .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; }
    .stat { padding: 14px 16px; }
    .stat strong { display: block; font-size: 24px; margin-bottom: 2px; }
    .stat span { color: var(--muted); font-size: 13px; }
    form.scan { display: flex; gap: 10px; align-items: center; justify-content: flex-end; flex-wrap: wrap; }
    button { border: 0; border-radius: 7px; background: var(--accent); color: #fff; cursor: pointer;
             display: inline-flex; align-items: center; min-height: 40px; padding: 0 14px;
             font-weight: 700; white-space: nowrap; }
    label { color: var(--muted); font-size: 14px; display: inline-flex; align-items: center; gap: 6px; }
    .filters { display: flex; gap: 10px; align-items: center; margin: 16px 0; flex-wrap: wrap; }
    .filters a { color: var(--ink); background: #fff; border: 1px solid var(--line);
                 border-radius: 999px; padding: 8px 12px; text-decoration: none; font-size: 14px; }
    .filters a.active { background: var(--ink); color: #fff; border-color: var(--ink); }
    .panel { overflow: hidden; }
    table { width: 100%; border-collapse: collapse; direction: rtl; }
    th, td { border-bottom: 1px solid var(--line); padding: 13px 12px; text-align: right;
             vertical-align: top; font-size: 14px; }
    th { background: #fbfcfe; color: #475467; font-size: 12px; position: sticky; top: 0; z-index: 1; }
    tr:last-child td { border-bottom: 0; }
    .title { font-weight: 700; max-width: 360px; }
    .desc { color: var(--muted); max-width: 440px; line-height: 1.45; }
    .badge { border-radius: 999px; display: inline-block; font-weight: 700; padding: 6px 9px; white-space: nowrap; }
    .yes { background: #ccfbf1; color: var(--good); }
    .no  { background: #ffe4e6; color: var(--bad); }
    .alive   { background: #dcfce7; color: #166534; }
    .dead    { background: #fee2e2; color: #991b1b; }
    .unknown { background: #fef9c3; color: #854d0e; }
    .pending { background: #e5e7eb; color: #4b5563; }
    .hot     { background: #ffedd5; color: #9a3412; border: 1px solid #fdba74; }
    .new     { background: #2563eb; color: #fff; }
    .scan-status { color: var(--muted); font-size: 13px; align-self: center; }
    .terms { color: #3730a3; background: var(--chip); border-radius: 6px; display: inline-block;
             max-width: 360px; padding: 6px 8px; line-height: 1.45; }
    a.link { color: var(--accent); direction: ltr; display: inline-block; max-width: 260px; overflow-wrap: anywhere; }
    .empty { padding: 42px; text-align: center; color: var(--muted); }
    @media (max-width: 860px) {
      .toolbar, .stats { grid-template-columns: 1fr; }
      .panel { overflow-x: auto; }
      table { min-width: 900px; }
      main { padding: 16px; }
    }
  </style>
</head>
<body>
  <header>
    <h1>מערכת חיפוש משרות</h1>
    <p class="subtitle">Junior R&D · Lab Technician · Mechanical Engineer · Medical Engineer — ישראל</p>
  </header>

  <main>
    <section class="toolbar">
      <div class="stats">
        <div class="stat"><strong>{{ relevant }}</strong><span>מתאימות לפרופיל</span></div>
        <div class="stat"><strong>{{ live }}</strong><span>מתאימות ופעילות</span></div>
        <div class="stat"><strong>🔥 {{ hot }}</strong><span>לוהטות (B.Sc. הנדסה רפואית)</span></div>
        <div class="stat"><strong>{{ shown }}</strong><span>מוצגות כרגע</span></div>
      </div>

      <div class="scan">
        <span id="scan-status" class="scan-status"></span>
        <form class="scan" method="post" action="{{ url_for('verify') }}">
          <button type="submit" style="background:var(--good)">בדוק תוקף משרות</button>
        </form>
        <form id="scan-form" class="scan" method="post" action="{{ url_for('scan') }}">
          <label><input type="checkbox" name="sample" value="1"> דוגמה בלבד</label>
          <button id="scan-btn" type="submit">הרץ סריקה</button>
        </form>
      </div>
    </section>

    <script>
      // Async scan: start it, then poll status and reload when finished.
      const form = document.getElementById('scan-form');
      const statusEl = document.getElementById('scan-status');
      const btn = document.getElementById('scan-btn');
      function poll() {
        fetch('{{ url_for("scan_status") }}').then(r => r.json()).then(s => {
          if (s.running) {
            btn.disabled = true;
            statusEl.textContent = '⏳ ' + (s.message || 'סורק…');
            setTimeout(poll, 3000);
          } else if (s.message) {
            statusEl.textContent = '✓ ' + s.message;
            btn.disabled = false;
            if (s.just_finished) location.reload();
          }
        }).catch(() => {});
      }
      if (form) form.addEventListener('submit', e => {
        e.preventDefault();
        fetch('{{ url_for("scan") }}', { method: 'POST', body: new FormData(form) })
          .then(() => { statusEl.textContent = '⏳ הסריקה התחילה…'; btn.disabled = true; setTimeout(poll, 1500); });
      });
      poll();  // reflect status on load (e.g. a scan triggered from the web)
    </script>

    <nav class="filters">
      <a class="{{ 'active' if view == 'hot'     else '' }}" href="{{ url_for('index', view='hot') }}">🔥 לוהטות</a>
      <a class="{{ 'active' if view == 'live'    else '' }}" href="{{ url_for('index', view='live') }}">מתאימות ופעילות</a>
      <a class="{{ 'active' if view == 'matched' else '' }}" href="{{ url_for('index', view='matched') }}">כל המתאימות</a>
      <a class="{{ 'active' if view == 'dead'    else '' }}" href="{{ url_for('index', view='dead') }}">פג תוקף</a>
      <a class="{{ 'active' if view == 'other'   else '' }}" href="{{ url_for('index', view='other') }}">לא מתאימות</a>
      <a class="{{ 'active' if view == 'all'     else '' }}" href="{{ url_for('index', view='all') }}">הכל</a>
    </nav>

    <section class="panel">
      {% if jobs %}
      <table>
        <thead>
          <tr>
            <th>התאמה</th><th>סטטוס</th><th>שם משרה</th><th>חברה</th><th>מיקום</th>
            <th>מקור</th><th>מילות התאמה</th><th>תיאור קצר</th>
            <th>קישור</th><th>נמצאה לאחרונה</th>
          </tr>
        </thead>
        <tbody>
        {% for job in jobs %}
          <tr>
            <td>
              {% if job.is_relevant %}
                <span class="badge yes">מתאימה</span>
              {% else %}
                <span class="badge no">לא</span>
              {% endif %}
            </td>
            <td>
              {% if job.is_new %}
                <span class="badge new">חדש</span>
              {% endif %}
              {% if job.is_hot %}
                <span class="badge hot" title="{{ job.hot_terms }}">🔥 לוהטת</span>
              {% endif %}
              {% if job.alive_status == 'alive' %}
                <span class="badge alive">פעילה</span>
              {% elif job.alive_status == 'dead' %}
                <span class="badge dead">פג תוקף</span>
              {% elif job.alive_status == 'unknown' %}
                <span class="badge unknown">לא ודאי</span>
              {% else %}
                <span class="badge pending">לא נבדק</span>
              {% endif %}
            </td>
            <td class="title">{{ job.title }}</td>
            <td>{{ job.company }}</td>
            <td>{{ job.location }}</td>
            <td>{{ job.source }}</td>
            <td>{% if job.matched_terms %}<span class="terms">{{ job.matched_terms }}</span>{% endif %}</td>
            <td class="desc">{{ job.description[:260] }}</td>
            <td><a class="link" href="{{ job.link }}" target="_blank" rel="noreferrer">פתיחה</a></td>
            <td dir="ltr">{{ job.last_seen_at[:19].replace('T', ' ') }}</td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
      {% else %}
        <div class="empty">אין עדיין משרות להצגה. לחץ על "הרץ סריקה".</div>
      {% endif %}
    </section>
  </main>
</body>
</html>
"""


def _config(dry_run: bool = False) -> Config:
    cfg = load_config()
    return Config(**{**asdict(cfg), "dry_run": dry_run}) if dry_run else cfg


@app.get("/")
def index():
    cfg = _config()
    store = JobStore(cfg.sqlite_path)
    all_jobs = store.list_jobs()
    view = request.args.get("view", "live")

    if view == "hot":
        visible = [j for j in all_jobs if j.is_relevant and j.is_hot]
    elif view == "live":
        visible = [j for j in all_jobs
                   if j.is_relevant and j.alive_status in ("alive", "unknown", "")]
    elif view == "matched":
        visible = [j for j in all_jobs if j.is_relevant]
    elif view == "dead":
        visible = [j for j in all_jobs if j.is_relevant and j.alive_status == "dead"]
    elif view == "other":
        visible = [j for j in all_jobs if not j.is_relevant]
    elif view == "all":
        visible = all_jobs
    else:
        view = "live"
        visible = [j for j in all_jobs
                   if j.is_relevant and j.alive_status in ("alive", "unknown", "")]

    total, relevant = store.count_jobs()
    live = store.count_live_relevant()
    hot = store.count_hot()
    return render_template_string(
        PAGE, jobs=visible, total=total, relevant=relevant, live=live, hot=hot,
        shown=len(visible), view=view,
    )


def _run_scan_job(use_sample: bool = False, requested_at: str = "") -> None:
    """Run a full scan in the background, then publish results to Firebase."""
    with _scan_lock:
        if _scan_state["running"]:
            return
        _scan_state.update(running=True, just_finished=False, message="סורק משרות…")
    publish_scan_status(True, "סורק משרות...", requested_at=requested_at)
    try:
        cfg = _config()
        found, new_relevant = run_scan(cfg, use_sample=use_sample)
        count = export_jobs_json(cfg.sqlite_path)  # writes jobs.json + pushes to RTDB
        publish_scan_status(
            False,
            f"הסריקה הושלמה: {count} משרות, {new_relevant} חדשות ורלוונטיות.",
            requested_at=requested_at,
            finished_at=datetime.now(timezone.utc).isoformat(),
            count=count,
            new_count=new_relevant,
        )
        msg = f"הסריקה הושלמה: {count} משרות, {new_relevant} חדשות ורלוונטיות."
    except Exception as exc:  # noqa: BLE001
        logging.exception("Scan failed: %s", exc)
        publish_scan_status(
            False,
            f"הסריקה נכשלה: {exc}",
            requested_at=requested_at,
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
        msg = f"הסריקה נכשלה: {exc}"
    with _scan_lock:
        _scan_state.update(running=False, just_finished=True, message=msg)


def _start_scan(use_sample: bool = False, requested_at: str = "") -> bool:
    with _scan_lock:
        if _scan_state["running"]:
            return False
    threading.Thread(
        target=_run_scan_job,
        kwargs={"use_sample": use_sample, "requested_at": requested_at},
                     daemon=True).start()
    return True


@app.post("/scan")
def scan():
    requested_at = datetime.now(timezone.utc).isoformat()
    started = _start_scan(
        use_sample=request.form.get("sample") == "1",
        requested_at=requested_at,
    )
    return jsonify(started=started, requestedAt=requested_at)


@app.get("/scan-status")
def scan_status():
    with _scan_lock:
        state = dict(_scan_state)
        _scan_state["just_finished"] = False  # consume the one-shot reload flag
    return jsonify(state)


@app.post("/verify")
def verify():
    """Re-check liveness of all relevant jobs already in the database."""
    from job_search_platform import verify_existing
    cfg = _config()
    verify_existing(JobStore(cfg.sqlite_path), cfg)
    export_jobs_json(cfg.sqlite_path)
    return redirect(url_for("index"))


def _scan_request_poller() -> None:
    """Watch Firebase RTDB for scan requests from the deployed dashboard and
    fulfill them locally (the static site can't run Python itself)."""
    last_seen = None
    while True:
        try:
            r = requests.get(f"{RTDB_URL}/scan_request.json", timeout=10)
            if r.status_code == 200 and r.json():
                req = r.json()
                stamp = req.get("requestedAt") if isinstance(req, dict) else None
                if stamp and stamp != last_seen:
                    last_seen = stamp
                    logging.info("Scan requested from dashboard at %s", stamp)
                    rtdb_put("scan_request/acceptedAt", datetime.now(timezone.utc).isoformat())
                    _start_scan(use_sample=False, requested_at=stamp)
        except requests.RequestException:
            pass
        time.sleep(15)


if __name__ == "__main__":
    threading.Thread(target=_scan_request_poller, daemon=True).start()
    app.run(host="127.0.0.1", port=5050, debug=False, threaded=True)
