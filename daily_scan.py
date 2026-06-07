from __future__ import annotations

from datetime import datetime, timezone

import job_search_platform as platform
from moran_profile import apply_moran_profile


def main() -> None:
    platform.setup_logging()
    apply_moran_profile(platform)
    requested_at = datetime.now(timezone.utc).isoformat()
    platform.publish_scan_status(True, "סריקה ידנית רצה...", requested_at=requested_at)
    try:
        config = platform.load_config()
        stats = platform.run_cloud_scan(config, use_sample=False)
        platform.publish_scan_status(
            False,
            f"הסריקה הושלמה: {stats['published']} משרות מוצגות, "
            f"{stats['new_relevant']} חדשות.",
            requested_at=requested_at,
            finished_at=datetime.now(timezone.utc).isoformat(),
            count=stats["published"],
            new_count=stats["new_relevant"],
        )
        print(
            "Done: "
            f"{stats['published']} published, {stats['new_relevant']} new, "
            f"{stats['scraped']} scraped, {stats['state']} in state."
        )
        jobs_data = platform.rtdb_get("jobs")
        if isinstance(jobs_data, list):
            jobs_list = jobs_data
        elif isinstance(jobs_data, dict):
            jobs_list = list(jobs_data.values())
        else:
            jobs_list = []
        if jobs_list:
            new_jobs = [j for j in jobs_list if isinstance(j, dict) and j.get("is_new")]
            if new_jobs:
                print(f"\n=== {len(new_jobs)} משרות חדשות מהסריקה הזו ===")
                for i, job in enumerate(new_jobs, 1):
                    title = job.get("title", "ללא כותרת")
                    company = job.get("company", "ללא חברה")
                    location = job.get("location", "")
                    hot = "[חם] " if job.get("is_hot") else ""
                    link = job.get("link", "")
                    print(f"{i:3}. {hot}{title} | {company} | {location}")
                    print(f"       {link}")
            print(f"\n=== רשימת {len(jobs_list)} משרות מתאימות ===")
            for i, job in enumerate(jobs_list, 1):
                if not isinstance(job, dict):
                    continue
                title = job.get("title", "ללא כותרת")
                company = job.get("company", "ללא חברה")
                location = job.get("location", "")
                hot = "[חם] " if job.get("is_hot") else ""
                new = "[חדש] " if job.get("is_new") else ""
                print(f"{i:3}. {new}{hot}{title} | {company} | {location}")
    except Exception as exc:  # noqa: BLE001
        platform.publish_scan_status(
            False,
            f"הסריקה נכשלה: {exc}",
            requested_at=requested_at,
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
        raise


if __name__ == "__main__":
    main()
