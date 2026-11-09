import json
import re
from functools import lru_cache

from .config import SKILLS_FILE


@lru_cache(maxsize=1)
def _patterns() -> dict[str, re.Pattern]:
    catalog: dict[str, list[str]] = json.loads(SKILLS_FILE.read_text(encoding="utf-8"))
    compiled = {}
    for skill, aliases in catalog.items():
        alts = sorted({a.lower() for a in aliases} | {skill.lower()}, key=len, reverse=True)
        body = "|".join(re.escape(a).replace(r"\ ", r"[\s\-]+") for a in alts)
        compiled[skill] = re.compile(rf"(?<![A-Za-z0-9_])(?:{body})(?![A-Za-z0-9_])(?![+#])", re.I)
    return compiled


def find_skills(text: str) -> set[str]:
    return {skill for skill, rx in _patterns().items() if rx.search(text)}


def compare_skills(job_skills: set[str], resume_skills: set[str]) -> tuple[list[str], list[str], list[str]]:
    matched = sorted(job_skills & resume_skills, key=str.lower)
    missing = sorted(job_skills - resume_skills, key=str.lower)
    other = sorted(resume_skills - job_skills, key=str.lower)[:12]
    return matched, missing, other
