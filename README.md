# Job Search Automation Platform

A modular Python platform that finds, filters, verifies, and tracks jobs for a
junior **Medical / Mechanical Engineering** candidate in Israel — focused on
roles posted in the **last month**.

## Architecture — NO-API direct web scraping

No Google API, SerpApi, or paid endpoints. The platform fetches and parses raw
HTML directly from job boards, with rotating browser-like headers to avoid
naive bot blocks.

**Sources**

| Source | How | Date filter |
|--------|-----|-------------|
| **LinkedIn** public guest job search | `requests` + `BeautifulSoup` on the unauthenticated `jobs-guest` search endpoint, paginated, keyword × `location=Israel` | last 30 days (`f_TPR=r2592000`) |
| **Greenhouse** public boards | parse server-rendered company board indexes for a curated list of Israeli companies | relevance + location |
| **Dynamic boards** (Comeet / Workday) | optional Playwright headless fallback for JS-rendered pages (`search_dynamic_boards`) | — |

**Pipeline**

1. **Scrape** every source (`scrape_all`) with header rotation and retry/backoff.
2. **Filter** client-side (`is_relevant_job`): enforces core skills/roles + Israeli
   locations, and excludes Senior / Lead / Manager / **Student / Intern** roles
   (word-boundary matched so `lead` ≠ `leadership`).
3. **Deduplicate** via SHA-1 of the job link in `jobs_seen.json` (`SeenStore`) so
   a posting is only processed once.
4. **Verify liveness + detect "hot"** (`verify_existing` → `inspect_jobs`): visits
   every relevant posting once and, from that same page, records two things:
   - **Liveness** — `alive` / `dead` / `unknown` by HTTP status, redirect target,
     and "no longer available" markers. Dead/expired postings are flagged.
   - **🔥 Hot** — whether the job *requirements* ask for Moran's degree, a
     **B.Sc. in Medical / Biomedical Engineering** (`evaluate_hotness`): the page
     must mention the field *and* a degree word (B.Sc / bachelor / תואר). Hot jobs
     are surfaced first and highlighted in both dashboards.
5. **Store** results in SQLite for the dashboard.

## Setup

```bash
pip install -r requirements.txt
python job_search_platform.py
```

Optional (only for JS-rendered Comeet/Workday boards):

```bash
pip install playwright && playwright install chromium
```

## Usage

```bash
python job_search_platform.py                 # full scrape + liveness verify
python job_search_platform.py --no-verify      # skip the liveness check
python job_search_platform.py --verify-only     # re-check existing DB jobs only
python job_search_platform.py --sample --dry-run # offline demo, no network
python -m unittest                              # run the test suite
```

## Web dashboard

```bash
python web_app.py     # → http://127.0.0.1:5050
```

Filters: **מתאימות ופעילות** (relevant & live), כל המתאימות, פג תוקף (expired),
לא מתאימות, הכל. Each row shows a liveness badge (פעילה / פג תוקף / לא ודאי).
Buttons: **הרץ סריקה** (run a scrape) and **בדוק תוקף משרות** (re-verify liveness).

## Tuning to the candidate

Edit the lists at the top of `job_search_platform.py`:

- `LINKEDIN_KEYWORDS` — search terms (English + Hebrew).
- `GREENHOUSE_COMPANIES` — Israeli companies whose boards to scrape.
- `TARGET_ROLES`, `KEYWORDS`, `LOCATIONS` — relevance filter.
- `NEGATIVE_TERMS` — roles to exclude (Senior, Student, …).

## Firebase Hosting (moran-cce72.web.app)

The dashboard is also published as a static site under `public/`, powered by the
Firebase JS SDK (loaded from CDN — no bundler needed). The Python scraper writes
the data feed to `public/jobs.json`, which the page fetches and renders.

**Files**

- `firebase.json` — Hosting config (serves `public/`, `jobs.json` is never cached).
- `.firebaserc` — pins the `moran-cce72` project.
- `public/index.html` — static dashboard with Moran's Firebase config + Analytics.
- `public/jobs.json` — generated data feed (relevant, non-expired jobs).

**1. Refresh the data feed** (runs the scrape, verifies liveness, exports JSON):

```bash
python job_search_platform.py                 # auto-writes public/jobs.json
# or, without re-scraping:
python job_search_platform.py --verify-only --export
```

**2. Install the Firebase CLI** (needs Node.js + npm):

```bash
npm install -g firebase-tools
```

**3. Log in and deploy** (these two steps are interactive — run them yourself):

```bash
firebase login
firebase deploy --only hosting
```

After deploying, the dashboard is live at **https://moran-cce72.web.app**.

### Interactive dashboard features

- **Expand/collapse**: click any job card to reveal its **full requirements text**
  (captured from the posting during inspection and stored in `requirements`).
- **🔥 Hot filter**: jobs whose requirements ask for a B.Sc. in Medical/Biomedical
  Engineering are badged and filterable.
- **"הגשתי" (Applied)** — backed by **Cloud Firestore**: clicking it writes a doc
  to the `applied` collection (`{link, title, company, appliedAt}`). Applied jobs
  move to the **✓ הגשתי** tab (with date) and are hidden from the other tabs.
  "בטל הגשה" removes them.

**One-time Firestore setup** (before the first deploy):

1. Enable Firestore (Native mode) at
   <https://console.firebase.google.com/project/moran-cce72/firestore>.
2. The security rules in `firestore.rules` (open access to the `applied`
   collection only) deploy automatically via `firebase deploy`.

> The page also initializes Firebase Analytics with the project's web config, so
> visits are tracked under the `moran` web app. Data is served from the static
> `jobs.json`; no Firestore credentials or service account are required.

## Daily execution (Windows Task Scheduler)

- Program: `python`
- Arguments: `C:\path\to\project\job_search_platform.py`
- Start in: `C:\path\to\project`

## Notes

Job-board markup changes over time. If a source returns zero results, inspect the
page and update the CSS selectors in the relevant `_parse_*` function.
