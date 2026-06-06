import json
import os
import requests
from job_search_platform import load_config, export_jobs_json, RTDB_URL

load_config()  # loads .env (FIREBASE_DB_SECRET)
secret = os.getenv("FIREBASE_DB_SECRET", "")
print("RTDB:", RTDB_URL, "| secret set:", bool(secret))

# 1. Deploy security rules via REST (admin secret bypasses locked rules).
with open("database.rules.json", encoding="utf-8") as fh:
    rules = json.load(fh)
r = requests.put(f"{RTDB_URL}/.settings/rules.json", params={"auth": secret},
                 data=json.dumps(rules), timeout=30)
print("Deploy rules ->", r.status_code, r.text[:160])

# 2. Push jobs + meta (uses the secret via push_to_rtdb).
cfg = load_config()
n = export_jobs_json(cfg.sqlite_path)
print("Exported/pushed jobs:", n)

# 3. Verify PUBLIC read (no auth) now works.
g = requests.get(f"{RTDB_URL}/meta.json", timeout=20)
print("Public GET /meta ->", g.status_code, g.text[:160])
gj = requests.get(f"{RTDB_URL}/jobs.json", timeout=30)
cnt = len(gj.json()) if gj.status_code == 200 and gj.json() else 0
print("Public GET /jobs ->", gj.status_code, "| jobs:", cnt)
