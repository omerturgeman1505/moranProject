from __future__ import annotations


EXTRA_LINKEDIN_KEYWORDS = [
    "Junior R&D Engineer",
    "R&D Lab Technician",
    "R&D Technician",
    "Biomedical Engineer",
    "Medical Engineer",
    "Junior Mechanical Engineer",
    "Bioprocess Engineer",
    "System Integration Engineer",
    "Validation Engineer",
    "Manufacturing Engineer Medical Device",
    "Application Engineer Medical Device",
    "מהנדסת מכשור רפואי",
    "מהנדסת מכונות",
    "מהנדס פיתוח",
    "מהנדסת פיתוח",
]

EXTRA_TARGET_ROLES = [
    "Junior Engineer",
    "R&D Lab Technician",
    "R&D Technician",
    "Mechanical Design Engineer",
    "Biomedical Engineer",
    "Medical Device Engineer",
    "Bioprocess Engineer",
    "System Integration Engineer",
    "Validation Engineer",
    "Manufacturing Engineer",
    "Application Engineer",
    "מהנדס פיתוח",
    "מהנדסת פיתוח",
]

EXTRA_KEYWORDS = [
    "prototype", "prototyping", "troubleshooting", "machine systems",
    "custom machine", "equipment", "biomedical engineer",
    "biomedical engineering", "physiologic", "physiological",
    "process optimization", "sop", "work instructions", "sterile",
    "laboratory", "lab equipment", "data analysis", "masterflex",
    "toc analyzer", "ionex", "wintercell", "dot systems", "dot system",
    "twin", "water saving", "large scale cell culture", "calibration",
    "calibrated", "iud", "inserter", "removal device", "afeka",
]

EXTRA_NEGATIVE_TERMS = [
    "freelance", "freelancer", "ai trainer", "trainer", "data annotation",
    "annotator", "content writer", "simulator", "simulation", "simulations",
    "gaming", "game engine", "unity", "unreal", "vr", "machine learning",
    "big data", "cloud", "wireless", "silicon", "soc", "mac layer",
    "bluetooth", "ble", "firmware", "signal processing", "software engineering",
    "algorithm development", "סימולטור", "סימולטורים", "סימולציה",
    "סימולציות", "מנועים גרפיים", "למידת מכונה", "מציאות מדומה",
]

HOT_PROFILE_SIGNALS = {
    "r_and_d": [
        "r&d", "research and development", "development engineer",
        "פיתוח",
    ],
    "junior_level": [
        "junior", "entry level", "graduate", "0-2", "0-3", "1-2", "1-3",
        "b.sc", "bsc", "bachelor", "תואר", "בוגר", "בוגרת",
    ],
    "medical_domain": [
        "medical device", "medical devices", "medical engineering",
        "biomedical", "physiologic", "physiological", "מכשור רפואי", "הנדסה רפואית",
    ],
    "mechanical_design": [
        "solidworks", "cad", "mechanical design", "3d printing",
        "prototype", "prototyping", "mechanical", "iud", "inserter",
        "removal device", "מכונות",
    ],
    "lab_bioprocess": [
        "bioreactor", "bioreactors", "cell culture", "tissue culture",
        "bioprocess", "cultivated", "sterile", "laboratory", "lab technician",
        "flexcell", "trubio", "cellaca", "cedex", "mfcs", "masterflex",
        "dot system", "dot systems", "twin", "large scale cell culture",
        "calibration", "calibrated",
    ],
    "process_data": [
        "process optimization", "process engineer", "validation", "sop",
        "work instructions", "data analysis",
    ],
    "systems_integration": [
        "system integration", "machine systems", "custom machine",
        "troubleshooting", "maintenance", "lab equipment", "reliability", "repeatability",
    ],
}


def _extend_unique(values: list[str], additions: list[str]) -> None:
    seen = {value.lower() for value in values}
    for value in additions:
        if value.lower() not in seen:
            values.append(value)
            seen.add(value.lower())


def apply_moran_profile(platform_module) -> None:
    """Tune the scanner to Moran's current CV before a cloud/manual scan."""
    _extend_unique(platform_module.LINKEDIN_KEYWORDS, EXTRA_LINKEDIN_KEYWORDS)
    _extend_unique(platform_module.TARGET_ROLES, EXTRA_TARGET_ROLES)
    _extend_unique(platform_module.KEYWORDS, EXTRA_KEYWORDS)
    _extend_unique(platform_module.NEGATIVE_TERMS, EXTRA_NEGATIVE_TERMS)
    _extend_unique(
        platform_module.MED_ENG_FIELDS,
        ["medical engineer", "biomedical engineer", "הנדסה ביו רפואית"],
    )
    _extend_unique(platform_module.DEGREE_WORDS, ["b.a.", "ב.סק"])

    def evaluate_hotness(text: str) -> tuple[bool, list[str]]:
        low = (text or "").lower()
        fields = [field for field in platform_module.MED_ENG_FIELDS if field in low]
        if fields and any(degree in low for degree in platform_module.DEGREE_WORDS):
            return True, fields

        matched_groups = [
            group for group, terms in HOT_PROFILE_SIGNALS.items()
            if any(term in low for term in terms)
        ]
        strong_groups = {
            "medical_domain", "mechanical_design", "lab_bioprocess",
            "process_data", "systems_integration",
        }
        has_role_or_level = bool({"r_and_d", "junior_level"} & set(matched_groups))
        strong_count = len(strong_groups & set(matched_groups))
        if strong_count >= 2 and (has_role_or_level or "medical_domain" in matched_groups):
            return True, matched_groups
        if strong_count >= 3:
            return True, matched_groups
        return False, []

    def analyze_moran_fit(job) -> tuple[str, str]:
        text = " ".join([
            job.title, job.company, job.location, job.source, job.description,
            job.matched_terms, job.hot_terms, job.requirements,
        ]).lower()
        if platform_module._has_negative_term(text):
            return "skip", "המשרה נראית בכירה/סטודנטיאלית מדי ולכן לא מוצגת כהתאמה."

        signals: list[str] = []
        score = 0
        if job.is_hot or evaluate_hotness(text)[0]:
            signals.append("מכילה שילוב חזק של דרישות שמתאים לפרופיל של מורן")
            score += 4
        if any(term in text for term in HOT_PROFILE_SIGNALS["medical_domain"]):
            signals.append("נוגעת למכשור רפואי או הנדסה רפואית")
            score += 3
        if any(term in text for term in HOT_PROFILE_SIGNALS["mechanical_design"]):
            signals.append("כוללת מכניקה/תכן/CAD שמתאימים לניסיון של מורן")
            score += 3
        if any(term in text for term in HOT_PROFILE_SIGNALS["lab_bioprocess"]):
            signals.append("כוללת מעבדה/ביוריאקטורים/תרביות תאים או ציוד שמוכר לה")
            score += 3
        if any(term in text for term in HOT_PROFILE_SIGNALS["systems_integration"]):
            signals.append("דורשת אינטגרציה, פתרון תקלות או עבודה עם מערכות מכניות מורכבות")
            score += 2
        if any(term in text for term in HOT_PROFILE_SIGNALS["process_data"]):
            signals.append("מתחברת לניסיון שלה באופטימיזציית תהליך, SOPs וניתוח נתונים")
            score += 2
        if any(role.lower() in text for role in platform_module.TARGET_ROLES):
            signals.append("שם התפקיד קרוב לכיוון המקצועי המבוקש")
            score += 2
        if any(loc in text for loc in platform_module.LOCATIONS):
            signals.append("המשרה בישראל")
            score += 1
        if any(term in text for term in HOT_PROFILE_SIGNALS["junior_level"]):
            signals.append("נראית מתאימה לרמת ג'וניור/בוגרת")
            score += 2
        if not signals and job.matched_terms:
            signals.append(f"זוהו מילות התאמה: {job.matched_terms}")
            score += 1

        if score >= 4:
            return "fit", "מתאימה למורן כי " + "; ".join(signals[:4]) + "."
        if score >= 2 or job.is_relevant:
            return "review", "פחות חזקה, אבל שווה בדיקה כי " + "; ".join(signals[:3]) + "."
        return "skip", "לא נמצאו מספיק סימנים שמחברים את המשרה לפרופיל של מורן."

    platform_module.evaluate_hotness = evaluate_hotness
    platform_module.analyze_moran_fit = analyze_moran_fit
