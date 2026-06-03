import unittest

from requirement_fit import (
    classify_degree,
    evaluate_fit,
    parse_degree_fields,
    parse_years_required,
    requires_master_degree,
)


class YearsTests(unittest.TestCase):
    def test_english_variants(self):
        self.assertEqual(parse_years_required("3+ years of experience"), 3)
        self.assertEqual(parse_years_required("Minimum 5 years experience"), 5)
        self.assertEqual(parse_years_required("at least 4 years"), 4)
        self.assertEqual(parse_years_required("2-4 years required"), 4)
        self.assertEqual(parse_years_required("4 years relevant experience"), 4)
        self.assertEqual(parse_years_required("experience of 4 years"), 4)
        self.assertEqual(parse_years_required("more than 3 years experience"), 3)
        self.assertEqual(parse_years_required("3 years or more"), 3)

    def test_hebrew_variants(self):
        self.assertEqual(parse_years_required("לפחות 4 שנות ניסיון"), 4)
        self.assertEqual(parse_years_required("3+ שנים בתעשייה"), 3)
        self.assertEqual(parse_years_required("מינימום 5 שנות ניסיון"), 5)
        self.assertEqual(parse_years_required("לפחות 3-5 שנות ניסיון בעבודה עם מנועים"), 5)
        self.assertEqual(parse_years_required("ניסיון של 4 שנים"), 4)
        self.assertEqual(parse_years_required("לפחות שלוש שנות ניסיון בניהול תהליכי פיתוח"), 3)
        self.assertEqual(parse_years_required("מעל ארבע שנות ניסיון"), 4)
        self.assertEqual(parse_years_required("3 שנים ומעלה"), 3)

    def test_none_when_absent(self):
        self.assertIsNone(parse_years_required("We are hiring engineers."))


class DegreeTests(unittest.TestCase):
    def test_detects_english_fields(self):
        f = parse_degree_fields("B.Sc. in Computer Science or Electrical Engineering")
        self.assertIn("computer science", f)
        self.assertIn("electrical engineering", f)

    def test_detects_hebrew_fields(self):
        f = parse_degree_fields("תואר ראשון בהנדסה רפואית או הנדסת מכונות")
        self.assertIn("הנדסה רפואית", f)
        self.assertIn("הנדסת מכונות", f)

    def test_classify_match_when_friendly_field_present(self):
        self.assertEqual(classify_degree(["biomedical engineering"]), "match")
        # Even if CS is also listed, a friendly field wins.
        self.assertEqual(classify_degree(["computer science", "biomedical engineering"]), "match")

    def test_classify_mismatch_when_only_cs_or_ee(self):
        self.assertEqual(classify_degree(["computer science"]), "mismatch")
        self.assertEqual(classify_degree(["electrical engineering"]), "mismatch")
        self.assertEqual(classify_degree(["מדעי המחשב"]), "mismatch")
        self.assertEqual(classify_degree(["הנדסת חשמל"]), "mismatch")
        self.assertEqual(classify_degree(["חשמל ואלקטרוניקה"]), "mismatch")
        self.assertEqual(classify_degree(["אוירונאוטיקה"]), "mismatch")

    def test_classify_unknown_when_no_field(self):
        self.assertEqual(classify_degree([]), "unknown")


class EvaluateFitTests(unittest.TestCase):
    def test_perfect_match(self):
        r = evaluate_fit("B.Sc. in Biomedical Engineering. 2 years experience.")
        self.assertEqual(r.fit_category, "fit")

    def test_too_many_years_rejects(self):
        r = evaluate_fit("Biomedical Engineering, 5+ years required.")
        self.assertEqual(r.fit_category, "no_fit")
        self.assertEqual(r.years_required, 5)

    def test_three_years_is_review(self):
        r = evaluate_fit("Biomedical Engineering, 3 years required.")
        self.assertEqual(r.fit_category, "review")

    def test_more_than_three_years_rejects(self):
        r = evaluate_fit("Biomedical Engineering, 4 years required.")
        self.assertEqual(r.fit_category, "no_fit")

    def test_cs_only_degree_rejects(self):
        r = evaluate_fit("B.Sc. in Computer Science required.")
        self.assertEqual(r.fit_category, "no_fit")
        self.assertIn("computer science", r.degree_fields)

    def test_hebrew_cs_rejects(self):
        r = evaluate_fit("דרישות: תואר ראשון במדעי המחשב")
        self.assertEqual(r.fit_category, "no_fit")

    def test_hebrew_ee_rejects(self):
        r = evaluate_fit("דרישות: תואר בהנדסת חשמל, ניסיון של 4 שנים")
        self.assertEqual(r.fit_category, "no_fit")

    def test_mixed_degrees_accepts(self):
        r = evaluate_fit("B.Sc. in Computer Science OR Biomedical Engineering")
        self.assertEqual(r.fit_category, "fit")

    def test_no_constraints_passes(self):
        r = evaluate_fit("Great team, fast-paced startup.")
        self.assertEqual(r.fit_category, "fit")


class MasterDegreeTests(unittest.TestCase):
    def test_explicit_msc_required(self):
        self.assertTrue(requires_master_degree("M.Sc. in Biomedical Engineering required"))
        self.assertTrue(requires_master_degree("Master's degree in Engineering"))
        self.assertTrue(requires_master_degree("MSc required"))
        self.assertTrue(requires_master_degree("graduate degree"))

    def test_hebrew_master_required(self):
        self.assertTrue(requires_master_degree("דרישות: תואר שני בהנדסה רפואית"))
        self.assertTrue(requires_master_degree("תואר שני בהנדסת מכונות"))

    def test_advantage_phrasing_is_not_required(self):
        self.assertFalse(requires_master_degree("M.Sc. - advantage"))
        self.assertFalse(requires_master_degree("Master's preferred"))
        self.assertFalse(requires_master_degree("M.Sc. is a plus"))
        self.assertFalse(requires_master_degree("M.Sc. nice to have"))
        self.assertFalse(requires_master_degree("תואר שני - יתרון"))
        self.assertFalse(requires_master_degree("תואר שני יתרון משמעותי"))

    def test_bsc_or_msc_not_a_block(self):
        self.assertFalse(requires_master_degree("B.Sc. or M.Sc. in Biomedical Engineering"))
        self.assertFalse(requires_master_degree("M.Sc. or B.Sc. in Biomedical Engineering"))
        self.assertFalse(requires_master_degree("B.Sc. / M.Sc. in Engineering"))
        self.assertFalse(requires_master_degree("Bachelor or Master in Engineering"))
        self.assertFalse(requires_master_degree("תואר ראשון או שני בהנדסה רפואית"))

    def test_no_master_mention(self):
        self.assertFalse(requires_master_degree("B.Sc. in Engineering. 2 years experience."))

    def test_evaluate_fit_marks_master_as_no_fit_with_flag(self):
        r = evaluate_fit("Requirements: M.Sc. in Biomedical Engineering")
        self.assertEqual(r.fit_category, "no_fit")
        self.assertTrue(r.requires_master)


if __name__ == "__main__":
    unittest.main()
