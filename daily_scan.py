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
