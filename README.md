# Moran Job Search

A lightweight job-search dashboard for Moran. The site is hosted on Firebase Hosting and reads jobs from Firebase Realtime Database. Job scans are run manually for free through GitHub Actions.

## Manual scan

1. Add the repository secret `FIREBASE_SERVICE_ACCOUNT_JSON` under `Settings -> Secrets and variables -> Actions`.
2. Paste the full Firebase service-account JSON as the secret value.
3. Open `Actions -> Moran Manual Job Scan`.
4. Click `Run workflow`.
5. Refresh https://moran-cce72.web.app after the workflow completes.

## What the scan updates

- `/job_state` - durable cloud state keyed by a hash of each job link.
- `/jobs` - public dashboard feed.
- `/meta` - generated timestamp and count.
- `/scan_status` - current/last scan status.
- `/applied` - jobs marked as applied from the dashboard.

## Retention

Jobs that are not marked as applied are removed from the public feed after 7 days. Applied jobs are retained so they remain visible in the applied tab.

## Local test

```bash
pip install -r requirements.txt
python daily_scan.py
```

For local runs, set `FIREBASE_SERVICE_ACCOUNT` to a local Firebase service-account JSON path. Do not commit service-account files.
