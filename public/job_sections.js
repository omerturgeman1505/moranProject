/** Client-side job summary parser — mirrors job_sections.py variant lists. */

export const SECTION_KEYS = {
  DESCRIPTION: "description",
  REQUIREMENTS: "requirements",
  RESPONSIBILITIES: "responsibilities",
  QUALIFICATIONS: "qualifications",
  BENEFITS: "benefits",
  ABOUT_COMPANY: "about_company",
  HOW_TO_APPLY: "how_to_apply",
  ADDITIONAL: "additional",
};

export const SECTION_UI_LABELS = {
  description: { he: "תיאור המשרה", en: "Job Description" },
  requirements: { he: "דרישות המשרה", en: "Requirements" },
  responsibilities: { he: "תחומי אחריות", en: "Responsibilities" },
  qualifications: { he: "השכלה וכישורים", en: "Qualifications" },
  benefits: { he: "יתרונות", en: "Benefits" },
  about_company: { he: "על החברה", en: "About the Company" },
  how_to_apply: { he: "הגשת מועמדות", en: "How to Apply" },
  additional: { he: "מידע נוסף", en: "Additional Information" },
};

export const SECTION_LABEL_VARIANTS = {
  description: [
    "תיאור", "תיאור המשרה", "תיאור התפקיד", "תיאור משרה", "על התפקיד", "על המשרה",
    "פרטי המשרה", "מה עושים בתפקיד", "התפקיד",
    "description", "job description", "role description", "position description",
    "about the role", "about this role", "about the job", "about this job",
    "the role", "overview", "summary", "position overview", "role overview",
  ],
  requirements: [
    "דרישות", "דרישות המשרה", "דרישות התפקיד", "דרישות חובה", "דרישות מינימום",
    "דרישות בסיס", "דרישות סף", "תנאי סף", "תנאים נדרשים", "כישורים נדרשים",
    "הכישורים הנדרשים", "מיומנויות נדרשות", "ידע נדרש", "השכלה נדרשת", "כישורים",
    "ניסיון נדרש", "פרופיל נדרש", "מה צריך", "מה נדרש", "מה דרוש",
    "מה אנחנו מחפשים", "מה אנחנו מחפשות",
    "requirements", "requirement", "job requirements", "role requirements",
    "the requirements", "required", "must have", "must-have", "must haves",
    "what you need", "what we need", "what you bring", "what you'll bring",
    "what you'll need", "what you will need", "what we're looking for",
    "what we are looking for", "who you are", "you have", "you should have",
    "you'll have", "you will have", "the ideal candidate", "ideal candidate",
    "your profile", "your background", "experience required",
    "requirements and qualifications", "requirements & qualifications",
    "skills and experience", "skills & experience", "minimum requirements",
    "essential requirements", "key requirements",
  ],
  responsibilities: [
    "תחומי אחריות", "אחריות", "משימות", "תפקידים", "מה תעשו", "מה תעשי",
    "responsibilities", "key responsibilities", "your responsibilities",
    "what you will do", "what you'll do", "what you do", "duties", "key duties",
    "day to day", "day-to-day",
  ],
  qualifications: [
    "השכלה", "הכשרה", "השכלה נדרשת", "כישורים מקצועיים", "רקע אקדמי",
    "qualifications", "qualification", "minimum qualifications",
    "preferred qualifications", "basic qualifications", "required qualifications",
    "qualifications and skills", "qualifications & skills",
    "education", "educational background", "academic background",
    "education and experience", "degree", "degrees", "certifications",
    "certification", "skills", "technical skills", "professional skills",
  ],
  benefits: [
    "יתרונות", "יתרון", "מה מציעים", "מה אנחנו מציעים", "מה אנחנו מציעות",
    "הטבות", "תנאים", "תנאי העסקה", "תנאי שכר",
    "benefits", "benefit", "what we offer", "what you'll get", "what you will get",
    "perks", "compensation", "compensation & benefits", "compensation and benefits",
    "our offer", "why join us",
  ],
  about_company: [
    "על החברה", "החברה", "אודות", "אודות החברה",
    "about us", "about the company", "about our company", "who we are",
    "our company", "company overview",
  ],
  how_to_apply: [
    "הגשת מועמדות", "איך להגיש", "להגשת מועמדות",
    "how to apply", "apply", "application", "application process",
    "submit your application",
  ],
  additional: [
    "מידע נוסף", "פרטים נוספים", "הערות",
    "additional information", "additional info", "other information", "notes",
    "misc", "general",
  ],
};

export const ADVANTAGE_VARIANTS = [
  "יתרון", "יתרונות", "advantage", "advantages", "nice to have", "nice-to-have",
  "preferred", "plus", "bonus", "a plus", "would be a plus",
];

export const REQUIREMENT_LINE_PATTERNS = [
  /\bb\.?\s*sc\b/i, /\bb\.?\s*eng\b/i, /\bbachelor/i, /\bdegree\b/i,
  /\b\d+\+?\s*years?\b/i, /\bexperience\b/i, /\brequired\b/i, /\bmust\b/i,
  /\bproficient\b/i, /\bsolidworks\b/i, /\bcad\b/i, /\bpython\b/i, /\bmatlab\b/i,
  /תואר/, /ניסיון/, /חובה/, /דרוש/, /דרושה/, /נדרש/, /נדרשת/,
];

export const DEFAULT_SECTION_ORDER = [
  "description", "responsibilities", "requirements", "qualifications",
  "benefits", "about_company", "how_to_apply", "additional",
];

const HEADER_PREFIX_RE = /^[\s#*•\-–—\d.)]+/;

function normalizeHeader(line) {
  let text = (line || "").trim();
  text = text.replace(HEADER_PREFIX_RE, "");
  text = text.replace(/[:：\-–—•*#]+$/, "").trim();
  text = text.replace(/\s+/g, " ").toLowerCase();
  return text;
}

const VARIANT_LOOKUP = (() => {
  const lookup = new Map();
  for (const [key, variants] of Object.entries(SECTION_LABEL_VARIANTS)) {
    for (const variant of variants) lookup.set(normalizeHeader(variant), key);
  }
  return lookup;
})();

export function matchSectionKey(line) {
  const normalized = normalizeHeader(line);
  if (!normalized) return null;
  if (VARIANT_LOOKUP.has(normalized)) return VARIANT_LOOKUP.get(normalized);
  for (const [variant, key] of VARIANT_LOOKUP.entries()) {
    if (variant.length >= 4 && (
      normalized === variant ||
      normalized.startsWith(variant + " ") ||
      normalized.endsWith(" " + variant)
    )) return key;
  }
  return null;
}

export function isAdvantageHeader(line) {
  const normalized = normalizeHeader(line);
  return ADVANTAGE_VARIANTS.some(v => normalizeHeader(v) === normalized);
}

export function detectLineLanguage(line) {
  let hebrew = 0, latin = 0;
  for (const ch of line) {
    const code = ch.charCodeAt(0);
    if (code >= 0x0590 && code <= 0x05ff) hebrew++;
    else if (ch >= "A" && ch <= "Z" || ch >= "a" && ch <= "z") latin++;
  }
  if (hebrew && !latin) return "he";
  if (latin && !hebrew) return "en";
  if (hebrew > latin * 2) return "he";
  if (latin > hebrew * 2) return "en";
  return "mixed";
}

function looksLikeRequirementLine(line) {
  const low = line.toLowerCase();
  return REQUIREMENT_LINE_PATTERNS.some(re => re.test(low));
}

function emptySections() {
  const blocks = {};
  for (const key of DEFAULT_SECTION_ORDER) blocks[key] = { he: [], en: [] };
  return blocks;
}

function appendLine(blocks, section, line) {
  const lang = detectLineLanguage(line);
  if (lang === "he") blocks[section].he.push(line);
  else if (lang === "en") blocks[section].en.push(line);
  else { blocks[section].he.push(line); blocks[section].en.push(line); }
}

function hasContent(block) {
  return (block.he && block.he.length) || (block.en && block.en.length);
}

function splitInlineHeader(line) {
  // "<section header>: <content>" → [key, content]. Only short heads count, so
  // prose lines that merely contain a colon are left untouched.
  const m = line.match(/[:：]/);
  if (!m) return null;
  const idx = line.indexOf(m[0]);
  const head = line.slice(0, idx).trim();
  const rest = line.slice(idx + 1).trim();
  if (!head || head.length > 40) return null;
  const key = matchSectionKey(head);
  if (!key) return null;
  return [key, rest];
}

export function parseJobSummary(text) {
  const blocks = emptySections();
  let current = "description";
  const lines = (text || "").split(/\n+/).map(x => x.trim()).filter(Boolean);

  for (const line of lines) {
    const inline = splitInlineHeader(line);
    if (inline) {
      current = inline[0];
      if (inline[1]) appendLine(blocks, current, inline[1]);
      continue;
    }
    const key = matchSectionKey(line);
    if (key) { current = key; continue; }
    if (isAdvantageHeader(line)) { current = "benefits"; continue; }
    appendLine(blocks, current, line);
  }

  if (!hasContent(blocks.requirements) && hasContent(blocks.description)) {
    for (const lang of ["he", "en"]) {
      const src = blocks.description[lang];
      if (!src.length) continue;
      const kept = [];
      for (const line of src) {
        if (looksLikeRequirementLine(line)) blocks.requirements[lang].push(line);
        else kept.push(line);
      }
      blocks.description[lang] = kept;
    }
  }

  if (!DEFAULT_SECTION_ORDER.some(k => hasContent(blocks[k]))) {
    blocks.additional.he.push("פתחי את עמוד המשרה לצפייה בדרישות המלאות.");
  }

  const out = {};
  for (const key of DEFAULT_SECTION_ORDER) {
    if (hasContent(blocks[key])) out[key] = blocks[key];
  }
  return out;
}

export function sectionDisplayLabel(key, locale = "he") {
  const labels = SECTION_UI_LABELS[key] || {};
  const loc = locale.startsWith("he") ? "he" : "en";
  return labels[loc] || labels.en || key;
}

export function formatBilingualBlock(block) {
  if (!block) return "";
  const parts = [];
  if (block.he && block.he.length) parts.push(block.he.join("\n"));
  if (block.en && block.en.length) {
    const enText = block.en.join("\n");
    if (!parts.length || parts[parts.length - 1] !== enText) parts.push(enText);
  }
  return parts.join("\n\n");
}
