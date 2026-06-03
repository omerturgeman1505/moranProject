import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from job_search_platform import (
    ALIVE,
    DEAD,
    UNKNOWN,
    Config,
    Job,
    JobStore,
    ProcessedJobStore,
    SeenStore,
    StoredJob,
    _is_job_posting_url,
    _parse_career_page,
    analyze_moran_fit,
    _parse_linkedin,
    absolute_url,
    check_job_alive,
    dedupe_jobs_in_memory,
    evaluate_hotness,
    infer_company_from_link,
    is_relevant_job,
    process_jobs,
    should_publish_job,
)


def test_config(sqlite_path: str) -> Config:
    return Config(
        google_api_key="",
        google_cx="",
        sqlite_path=sqlite_path,
        request_timeout_seconds=1,
        sheets_enabled=False,
        google_sheet_id="",
        google_sheet_name="Jobs",
        google_service_account_file="",
        google_service_account_json="",
        dry_run=True,
    )


class JobSearchPlatformTests(unittest.TestCase):
    def test_relevance_filter_accepts_candidate_match(self) -> None:
        job = Job(
            title="Junior Mechanical Engineer",
            company="Medical Devices Ltd",
            location="Rehovot, Israel",
            link="https://example.com/job/1",
            source="unit",
            description="SolidWorks, CAD, 3D printing, MATLAB",
        )

        self.assertTrue(is_relevant_job(job))

    def test_relevance_filter_rejects_unrelated_job(self) -> None:
        job = Job(
            title="Senior Finance Analyst",
            company="Bank",
            location="London",
            link="https://example.com/job/2",
            source="unit",
            description="Financial reporting",
        )

        self.assertFalse(is_relevant_job(job))

    def test_parse_career_page_extracts_biomed_roles(self) -> None:
        html = """
        <main>
          <section>
            <h3>Mechanical Design Engineer</h3>
            <p>Medical Device R&D role in Haifa, Israel.</p>
            <p>B.Sc. Biomedical or Mechanical Engineering. SolidWorks.</p>
          </section>
          <section>
            <h3>Marketing Manager</h3>
            <p>Sales collateral and campaigns.</p>
          </section>
        </main>
        """

        jobs = _parse_career_page(
            html,
            company="MedCo",
            url="https://example.com/careers/",
            domain="Medical Device",
        )

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].title, "Mechanical Design Engineer")
        self.assertIn("Medical Device", jobs[0].description)

    def test_dedupes_by_link(self) -> None:
        jobs = [
            Job("A", "C", "Israel", "https://example.com/1", "unit"),
            Job("B", "C", "Israel", "https://example.com/1", "unit"),
            Job("C", "C", "Israel", "https://example.com/2", "unit"),
        ]

        self.assertEqual(len(dedupe_jobs_in_memory(jobs)), 2)

    def test_sqlite_tracking_prevents_duplicate_processing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            sqlite_path = str(Path(temp_dir) / "jobs.sqlite3")
            config = test_config(sqlite_path)
            store = ProcessedJobStore(sqlite_path)
            job = Job(
                title="Junior Medical Engineer",
                company="Lab",
                location="Tel Aviv, Israel",
                link="https://example.com/job/3",
                source="unit",
                description="Python, MATLAB, bioreactors",
            )

            self.assertEqual(process_jobs(config, store, [job]), 1)
            self.assertEqual(process_jobs(config, store, [job]), 0)

    def test_helpers(self) -> None:
        self.assertEqual(
            absolute_url("https://example.com/jobs?q=x", "/job/123"),
            "https://example.com/job/123",
        )
        self.assertEqual(
            infer_company_from_link("https://boards.greenhouse.io/acme/jobs/123"),
            "Acme",
        )

    def test_job_posting_url_filter(self) -> None:
        # Real individual postings are kept.
        self.assertTrue(_is_job_posting_url("https://boards.greenhouse.io/acme/jobs/123"))
        self.assertTrue(_is_job_posting_url("https://jobs.lever.co/acme/uuid-here"))
        self.assertTrue(_is_job_posting_url("https://acme.wd5.myworkdayjobs.com/x/job/Israel/Eng_R1"))
        # Board index pages and unrelated URLs are rejected.
        self.assertFalse(_is_job_posting_url("https://boards.greenhouse.io/acme"))
        self.assertFalse(_is_job_posting_url("https://example.com/careers"))

    def test_check_job_alive_statuses(self) -> None:
        def fake_get(status_code, text="", url="https://boards.greenhouse.io/acme/jobs/1"):
            resp = mock.Mock()
            resp.status_code = status_code
            resp.text = text
            resp.url = url
            return resp

        link = "https://boards.greenhouse.io/acme/jobs/1"
        with mock.patch("job_search_platform.requests.get", return_value=fake_get(200, "Apply now")):
            self.assertEqual(check_job_alive(link), ALIVE)
        with mock.patch("job_search_platform.requests.get", return_value=fake_get(404)):
            self.assertEqual(check_job_alive(link), DEAD)
        with mock.patch("job_search_platform.requests.get",
                        return_value=fake_get(200, "This job is no longer available")):
            self.assertEqual(check_job_alive(link), DEAD)
        with mock.patch("job_search_platform.requests.get", return_value=fake_get(429)), \
                mock.patch("job_search_platform.time.sleep"):
            self.assertEqual(check_job_alive(link), UNKNOWN)

    def test_excludes_senior_and_student(self) -> None:
        senior = Job("Senior Mechanical Engineer", "Co", "Tel Aviv, Israel",
                     "https://x/1", "unit", "SolidWorks CAD")
        student = Job("Student Position - Mechanical", "Co", "Haifa, Israel",
                      "https://x/2", "unit", "CAD")
        self.assertFalse(is_relevant_job(senior))
        self.assertFalse(is_relevant_job(student))

    def test_negative_word_boundary(self) -> None:
        # 'leadership' should NOT trigger the 'lead' negative.
        job = Job("Mechanical Engineer", "Co", "Rehovot, Israel",
                  "https://x/3", "unit", "Strong CAD skills and leadership mindset")
        self.assertTrue(is_relevant_job(job))

    def test_seen_store_dedup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = str(Path(temp_dir) / "jobs_seen.json")
            seen = SeenStore(path)
            self.assertFalse(seen.has_seen("https://x/job/1"))
            seen.mark_seen("https://x/job/1")
            seen.save()
            # New instance loads from disk.
            self.assertTrue(SeenStore(path).has_seen("https://x/job/1"))

    def test_parse_linkedin_card(self) -> None:
        html = """
        <ul><li>
          <a class="base-card__full-link" href="https://il.linkedin.com/jobs/view/mechanical-engineer-at-hp-123?x=1">x</a>
          <h3 class="base-search-card__title">Mechanical Engineer</h3>
          <h4 class="base-search-card__subtitle"><a>HP</a></h4>
          <span class="job-search-card__location">Ness Ziona, Israel</span>
        </li></ul>
        """
        jobs = _parse_linkedin(html)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].title, "Mechanical Engineer")
        self.assertEqual(jobs[0].company, "HP")
        self.assertEqual(jobs[0].link, "https://il.linkedin.com/jobs/view/mechanical-engineer-at-hp-123")

    def test_hotness_requires_degree_and_field(self) -> None:
        # Field + degree word ⇒ hot.
        hot, terms = evaluate_hotness("Requirements: B.Sc. in Medical Engineering")
        self.assertTrue(hot)
        self.assertIn("medical engineering", terms)
        # Hebrew variant.
        hot_he, _ = evaluate_hotness("דרישות: תואר ראשון בהנדסה רפואית")
        self.assertTrue(hot_he)
        # Field with no degree word ⇒ not hot.
        self.assertFalse(evaluate_hotness("Join our medical engineering team!")[0])
        # Unrelated text ⇒ not hot.
        self.assertFalse(evaluate_hotness("B.Sc. in Computer Science")[0])

    def test_hotness_accepts_cv_signal_combination(self) -> None:
        hot, terms = evaluate_hotness(
            "Junior R&D Engineer role with SolidWorks, bioreactor integration, "
            "process optimization, troubleshooting and lab equipment."
        )

        self.assertTrue(hot)
        self.assertIn("mechanical_design", terms)
        self.assertIn("lab_bioprocess", terms)

    def test_hot_state_persists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            sqlite_path = str(Path(temp_dir) / "jobs.sqlite3")
            store = JobStore(sqlite_path)
            job = Job("R&D Engineer", "MedCo", "Rehovot, Israel",
                      "https://x/job/hot", "unit", "SolidWorks")
            store.upsert_job(job)
            store.update_inspection(job.link, ALIVE, True, "biomedical engineering")
            stored = store.list_jobs()[0]
            self.assertTrue(stored.is_hot)
            self.assertEqual(stored.hot_terms, "biomedical engineering")
            self.assertEqual(store.count_hot(), 1)

    def test_moran_fit_reason_for_strong_match(self) -> None:
        job = StoredJob(
            title="Junior R&D Mechanical Engineer",
            company="MedCo",
            location="Rehovot, Israel",
            link="https://x/job/fit",
            source="unit",
            description="Medical devices, SolidWorks and CAD",
            is_relevant=True,
            matched_terms="medical device, solidworks, cad, rehovot",
            first_seen_at="",
            last_seen_at="",
            alive_status=ALIVE,
            is_hot=True,
            hot_terms="biomedical engineering",
            requirements="B.Sc. in Biomedical Engineering. Mechanical design.",
        )

        category, reason = analyze_moran_fit(job)

        self.assertEqual(category, "fit")
        self.assertIn("מורן", reason)

    def test_moran_fit_for_process_engineering_match(self) -> None:
        job = StoredJob(
            title="Process Engineer",
            company="FoodTech",
            location="Israel",
            link="https://x/job/review",
            source="unit",
            description="Validation and process work",
            is_relevant=True,
            matched_terms="process engineer, israel",
            first_seen_at="",
            last_seen_at="",
            alive_status=UNKNOWN,
            requirements="Process documentation and production support.",
        )

        category, reason = analyze_moran_fit(job)

        self.assertEqual(category, "fit")
        self.assertIn("מורן", reason)

    def test_moran_fit_review_for_weaker_match(self) -> None:
        job = StoredJob(
            title="Operations Associate",
            company="MedCo",
            location="Israel",
            link="https://x/job/review",
            source="unit",
            description="Support validation documentation and Excel tracking.",
            is_relevant=True,
            matched_terms="validation, israel",
            first_seen_at="",
            last_seen_at="",
            alive_status=UNKNOWN,
            requirements="Documentation support and production coordination.",
        )

        category, reason = analyze_moran_fit(job)

        self.assertEqual(category, "review")
        self.assertIn("שווה בדיקה", reason)

    def test_moran_fit_skips_engine_role_with_too_many_years(self) -> None:
        job = StoredJob(
            title="מהנדס/ת מנועים",
            company="IAI",
            location="Lod, Israel",
            link="https://x/job/engines",
            source="unit",
            description="מערכות הנעה ומנועי בוכנה",
            is_relevant=True,
            matched_terms="israel, מהנדס",
            first_seen_at="",
            last_seen_at="",
            alive_status=ALIVE,
            requirements=(
                "תואר ראשון בהנדסת מכונות/אווירונאוטיקה- חובה\n"
                "לפחות 3-5 שנות ניסיון בעבודה עם מנועים- חובה"
            ),
        )

        category, _reason = analyze_moran_fit(job)

        self.assertEqual(category, "skip")

    def test_moran_fit_skips_wireless_simulator_role(self) -> None:
        job = StoredJob(
            title="BT MAC System Integration Engineer",
            company="Apple",
            location="Haifa, Israel",
            link="https://x/job/wireless",
            source="unit",
            description="Wireless SoC, MAC layer, Bluetooth and silicon validation",
            is_relevant=True,
            matched_terms="python, integration, lab",
            first_seen_at="",
            last_seen_at="",
            alive_status=ALIVE,
            is_hot=True,
            requirements=(
                "B.Sc / M.Sc in Electrical / Computer Engineering or related fields\n"
                "3+ years of relevant experience\n"
                "Strong understanding of BT MAC layer protocol"
            ),
        )

        category, _reason = analyze_moran_fit(job)

        self.assertEqual(category, "skip")

    def test_old_non_applied_job_is_not_published(self) -> None:
        job = StoredJob(
            title="R&D Engineer",
            company="MedCo",
            location="Israel",
            link="https://x/job/old",
            source="unit",
            description="Medical device role",
            is_relevant=True,
            matched_terms="medical device, israel",
            first_seen_at=(datetime.now(timezone.utc) - timedelta(days=8)).isoformat(),
            last_seen_at="",
        )

        self.assertFalse(should_publish_job(job, applied_links=set()))

    def test_old_applied_job_is_kept(self) -> None:
        job = StoredJob(
            title="R&D Engineer",
            company="MedCo",
            location="Israel",
            link="https://x/job/applied",
            source="unit",
            description="Medical device role",
            is_relevant=True,
            matched_terms="medical device, israel",
            first_seen_at=(datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),
            last_seen_at="",
        )

        self.assertTrue(should_publish_job(job, applied_links={job.link}))

    def test_alive_status_persists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            sqlite_path = str(Path(temp_dir) / "jobs.sqlite3")
            store = JobStore(sqlite_path)
            job = Job(
                title="Mechanical Engineer", company="Lab",
                location="Rehovot, Israel", link="https://example.com/job/9",
                source="unit", description="SolidWorks CAD",
            )
            store.upsert_job(job)
            store.update_alive_status(job.link, ALIVE)
            stored = store.list_jobs()[0]
            self.assertEqual(stored.alive_status, ALIVE)
            self.assertTrue(stored.alive_checked_at)


if __name__ == "__main__":
    unittest.main()
