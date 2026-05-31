from __future__ import annotations

from datetime import datetime, timezone

from job_search_platform import load_config, publish_scan_status, run_cloud_scan, setup_logging


def main() -> None:
    setup_logging()
    requested_at = datetime.now(timezone.utc).isoformat()
    publish_scan_status(True, "סריקה ידנית רצה...", requested_at=requested_at)
    try:
        config = load_config()
        stats = run_cloud_scan(config)
        publish_scan_status(
            False,
            f"הסריקה הושלמה: {stats['published']} משרות מוצגות, {stats['new_relevant']} חדשות.",
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
    except Exception as exc:  # noqa: BLE001
        publish_scan_status(
            False,
            f"הסריקה נכשלה: {exc}",
            requested_at=requested_at,
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
        raise


if __name__ == "__main__":
    main()
