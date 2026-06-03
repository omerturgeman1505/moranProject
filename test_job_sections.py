import unittest

from job_sections import (
    DEFAULT_SECTION_ORDER,
    SECTION_LABEL_VARIANTS,
    detect_line_language,
    match_section_key,
    parse_job_summary,
    section_display_label,
)


class JobSectionsTests(unittest.TestCase):
    def test_all_sections_have_variants(self) -> None:
        for key in DEFAULT_SECTION_ORDER:
            self.assertIn(key, SECTION_LABEL_VARIANTS)
            self.assertGreater(len(SECTION_LABEL_VARIANTS[key]), 3)

    def test_match_hebrew_and_english_headers(self) -> None:
        self.assertEqual(match_section_key("דרישות המשרה:"), "requirements")
        self.assertEqual(match_section_key("Job Description"), "description")
        self.assertEqual(match_section_key("**Requirements**"), "requirements")
        self.assertEqual(match_section_key("What you'll do"), "responsibilities")

    def test_parse_bilingual_posting(self) -> None:
        text = """Job Description
We are looking for a junior engineer.

Requirements
B.Sc. in Mechanical Engineering
2+ years experience

דרישות
תואר ראשון בהנדסת מכונות
ניסיון של שנה"""

        parsed = parse_job_summary(text)
        data = parsed.to_dict()

        self.assertIn("description", data)
        self.assertIn("requirements", data)
        self.assertTrue(any("junior engineer" in line.lower() for line in data["description"]["en"]))
        self.assertTrue(any("B.Sc." in line for line in data["requirements"]["en"]))
        self.assertTrue(any("תואר" in line for line in data["requirements"]["he"]))

    def test_heuristic_moves_degree_lines_to_requirements(self) -> None:
        text = """About the role
Great team and culture.
B.Sc. in Biomedical Engineering required."""

        data = parse_job_summary(text).to_dict()
        req_lines = data.get("requirements", {}).get("en", [])
        self.assertTrue(any("B.Sc." in line for line in req_lines))

    def test_advantage_header_goes_to_benefits(self) -> None:
        text = """Requirements
Must know Python.

Nice to have
SolidWorks experience"""

        data = parse_job_summary(text).to_dict()
        self.assertIn("benefits", data)
        self.assertTrue(any("SolidWorks" in line for line in data["benefits"]["en"]))

    def test_detect_line_language(self) -> None:
        self.assertEqual(detect_line_language("תואר ראשון בהנדסה"), "he")
        self.assertEqual(detect_line_language("B.Sc. required"), "en")

    def test_section_display_label(self) -> None:
        self.assertEqual(section_display_label("requirements", "he"), "דרישות המשרה")
        self.assertEqual(section_display_label("requirements", "en"), "Requirements")
        self.assertEqual(section_display_label("benefits", "he"), "יתרונות")

    def test_inline_header_keeps_content_english(self) -> None:
        text = """About the role
We build surgical robots.
Requirements: B.Sc. in Biomedical Engineering and SolidWorks."""
        data = parse_job_summary(text).to_dict()
        req = data.get("requirements", {}).get("en", [])
        self.assertTrue(any("B.Sc." in line for line in req))
        # The description must NOT contain the requirements content.
        desc = data.get("description", {}).get("en", [])
        self.assertFalse(any("B.Sc." in line for line in desc))

    def test_inline_header_keeps_content_hebrew(self) -> None:
        text = """תיאור המשרה
חברת מכשור רפואי מובילה.
דרישות: תואר ראשון בהנדסה רפואית, ניסיון בסולידוורקס."""
        data = parse_job_summary(text).to_dict()
        req = data.get("requirements", {}).get("he", [])
        self.assertTrue(any("תואר" in line for line in req))

    def test_colon_in_prose_is_not_a_header(self) -> None:
        # A long prose line with a colon should stay in the description.
        text = "We are a fast-growing medical device company: come build with us."
        data = parse_job_summary(text).to_dict()
        self.assertIn("description", data)
        self.assertTrue(any("medical device company" in l for l in data["description"]["en"]))

    def test_new_boundary_words(self) -> None:
        self.assertEqual(match_section_key("Who you are"), "requirements")
        self.assertEqual(match_section_key("דרישות סף:"), "requirements")
        self.assertEqual(match_section_key("Preferred Qualifications"), "qualifications")

    def test_empty_text_fallback(self) -> None:
        data = parse_job_summary("").to_dict()
        self.assertIn("additional", data)
        self.assertTrue(data["additional"]["he"])


if __name__ == "__main__":
    unittest.main()
