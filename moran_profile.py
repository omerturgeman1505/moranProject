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
    # Biomedical-focused searches
    "Biomedical R&D Engineer",
    "R&D Engineer Medical Device",
    "Junior Biomedical Engineer",
    "Clinical Engineer",
    "Quality Engineer Medical Device",
    "V&V Engineer",
    "Verification and Validation Engineer",
    "Product Engineer Medical Device",
    "Field Service Engineer Medical Device",
    "Biomedical Equipment Technician",
    "Medical Device Assembler Engineer",
    "מהנדס ביו רפואי",
    "מהנדסת ביו רפואית",
    "הנדסה ביו רפואית",
    "הנדסה רפואית",
    "מהנדס ולידציה",
    "מהנדסת ולידציה",
    "מהנדס איכות מכשור רפואי",
    "מהנדסת איכות מכשור רפואי",
    # Cell culture / bioprocess (Moran's lab background)
    "Cell Culture Technician",
    "Cell Culture Engineer",
    "Upstream Process Development Engineer",
    "Downstream Process Development",
    "Bioprocess Development Engineer",
    "Bioreactor Technician",
    "Lab Technician Cell Culture",
    "R&D Technician Bioprocess",
    "Cultivated Meat Engineer",
    "Food Tech Engineer Israel",
    # Process / production engineering
    "Process Development Engineer Medical Device",
    "Process Validation Engineer",
    "Manufacturing Process Engineer",
    "Production Engineer Medical Device",
    "Quality Assurance Engineer Medical Device",
    "Regulatory Affairs Engineer Israel",
    # More Hebrew searches
    "מהנדס תהליך",
    "מהנדסת תהליך",
    "מהנדס ייצור",
    "מהנדסת ייצור",
    "מהנדס איכות",
    "מהנדסת איכות",
    "מהנדס מערכות",
    "מהנדסת מערכות",
    "טכנאי מעבדה",
    "טכנאית מעבדה",
    "תרביות תאים",
    "ביוריאקטור",
    "מהנדס אינטגרציה",
    "מהנדסת אינטגרציה",
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
    # Biomedical-focused roles
    "Biomedical R&D Engineer",
    "Clinical Engineer",
    "V&V Engineer",
    "Verification Engineer",
    "Quality Engineer",
    "Field Service Engineer",
    "מהנדס ביו רפואי",
    "מהנדסת ביו רפואית",
    "מהנדס רפואי",
    "מהנדסת רפואית",
    "מהנדס ולידציה",
    "מהנדסת ולידציה",
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
    # Biomedical / medical device domain
    "v&v", "verification and validation", "design verification",
    "iso 13485", "fda", "ce mark", "mdr", "design control",
    "clinical", "implant", "implants", "catheter", "surgical",
    "diagnostics", "imaging", "ultrasound", "patient monitoring",
    "מכשור רפואי", "ציוד רפואי", "אביזר רפואי", "השתלים", "שתלים",
    "קליני", "קלינית", "רגולציה רפואית",
    # Cell culture / bioprocess / cultivated meat
    "upstream", "downstream", "upstream process", "downstream process",
    "cell line", "cell lines", "mammalian cell", "cho cells",
    "perfusion", "fed-batch", "batch culture", "scale-up",
    "cultivated meat", "alt protein", "alternative protein",
    "fermentation", "fermentor", "fermenter", "upstream bioreactor",
    "תרביות תאים", "ביוריאקטור", "ביוריאקטורים", "קנה מידה",
    "בשר מתורבת", "חלבון חלופי",
    # Mechanical / IVD / lab instruments
    "gage", "gauge", "gmp", "gmp compliance",
    "design history file", "dhf", "risk management", "iso 14971",
    "usability", "human factors", "test protocol",
    "assembly", "jig", "fixture", "pump", "flow control",
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
        "iso 13485", "design control", "clinical", "implant", "catheter",
        "surgical", "patient monitoring", "diagnostics",
        "ציוד רפואי", "אביזר רפואי", "שתלים", "קליני", "קלינית",
        "הנדסה ביו רפואית", "הנדסה ביו-רפואית", "הנדסה ביורפואית",
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
        # Cell culture / upstream/downstream
        "upstream", "downstream", "scale-up", "fed-batch", "perfusion",
        "cell line", "mammalian cell", "cho", "fermentation", "fermenter",
        "cultivated meat", "alt protein", "alternative protein",
        "תרביות תאים", "ביוריאקטור", "ביוריאקטורים", "בשר מתורבת",
    ],
    "process_data": [
        "process optimization", "process engineer", "validation", "sop",
        "work instructions", "data analysis",
        "gmp", "gmp compliance", "risk management", "iso 14971",
        "test protocol", "dhf", "design history file",
        "process development", "scale up", "process transfer",
    ],
    "systems_integration": [
        "system integration", "machine systems", "custom machine",
        "troubleshooting", "maintenance", "lab equipment", "reliability", "repeatability",
        "assembly", "jig", "fixture", "pump", "flow control",
        "mechanical assembly", "electromechanical",
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
    # Extend AllJobs keyword list when available
    if hasattr(platform_module, "ALLJOBS_KEYWORDS"):
        _extend_unique(platform_module.ALLJOBS_KEYWORDS, EXTRA_LINKEDIN_KEYWORDS)
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
        from requirement_fit import evaluate_fit

        if platform_module._has_job_level_negative(job):
            return "skip", "המשרה נראית בכירה/סטודנטיאלית מדי ולכן לא מוצגת כהתאמה."

        text = " ".join([
            job.title, job.company, job.location, job.source, job.description,
            job.matched_terms, job.hot_terms, job.requirements,
        ]).lower()

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
            category, reason = "fit", "מתאימה למורן כי " + "; ".join(signals[:4]) + "."
        elif score >= 2 or job.is_relevant:
            category, reason = "review", "פחות חזקה, אבל שווה בדיקה כי " + "; ".join(signals[:3]) + "."
        elif platform_module._has_biomedical_review_signal(text):
            category, reason = (
                "review",
                "פחות מתאימה, אבל שווה בדיקה כי היא בתחום biomedical/medical device ויש בה נקודת חיבור מקצועית לפרופיל של מורן."
            )
        else:
            return "skip", "לא נמצאו מספיק סימנים שמחברים את המשרה לפרופיל של מורן."

        clean_req = platform_module._clean_job_requirement_text(job.requirements)
        veto = evaluate_fit(clean_req or job.requirements or job.description or "")
        if veto.requires_master:
            return "skip", veto.reason
        if veto.fit_category == "no_fit":
            return "skip", veto.reason
        if veto.fit_category == "review" and category == "fit":
            return "review", f"{veto.reason}. " + reason
        return category, reason

    platform_module.evaluate_hotness = evaluate_hotness
    platform_module.analyze_moran_fit = analyze_moran_fit
