import job_search_platform as j
from requirement_fit import _MASTER_PATTERNS, _MASTER_ADVANTAGE_CUES, _MASTER_NON_REQUIREMENT_CUES
import re

cfg = j.load_config()
store = j.JobStore(cfg.sqlite_path)
qual = next((s for s in store.list_jobs() if "Qualcomm" in s.company), None)
txt = qual.requirements

# walk every pattern, every match, and report why we return True/False at each.
for i, pat in enumerate(_MASTER_PATTERNS):
    for m in pat.finditer(txt):
        start, end = m.span()
        window = txt[max(0, start-90):min(len(txt), end+90)].lower()
        if any(cue in window for cue in _MASTER_ADVANTAGE_CUES): r="advantage cue"
        elif any(cue in window for cue in _MASTER_NON_REQUIREMENT_CUES): r="non-req cue"
        elif re.search(r"\b(?:b\.?\s*sc|b\.?\s*eng|b\.?\s*a|bachelor)\b.{0,40}?\bor\b", window): r="BS or X"
        elif re.search(r"\bor\b.{0,40}?\b(?:m\.?\s*sc|m\.?\s*eng|master'?s?)\b", window): r="or master"
        elif "תואר ראשון או" in window: r="he"
        else: r="*** RETURN TRUE ***"
        print(f"#{i} {m.group()!r:18} @ {start}: {r}")
        print(f"   win: ...{window[:160]}...\n")
