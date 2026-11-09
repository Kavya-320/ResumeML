import re
from datetime import date
from typing import Optional

from .schemas import ExperienceInfo

EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9][A-Za-z0-9._%+\-]*@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,24}(?![A-Za-z0-9\-])"
)
PLACEHOLDER_DOMAINS = {"example.com", "domain.com", "email.com", "yourmail.com", "mail.com"}


def extract_email(text: str) -> Optional[str]:
    for match in EMAIL_RE.finditer(text):
        email = match.group(0).rstrip(".").lower()
        local, _, domain = email.partition("@")
        if ".." in email or local.endswith(".") or domain.startswith("-"):
            continue
        if domain in PLACEHOLDER_DOMAINS or local.startswith(("noreply", "no-reply")):
            continue
        return email
    return None


NAME_BLOCKLIST = {
    "resume", "curriculum", "vitae", "cv", "profile", "summary", "objective", "contact", "address",
    "engineer", "developer", "scientist", "analyst", "manager", "designer", "intern", "consultant",
    "architect", "specialist", "administrator", "experience", "education", "skills", "projects",
    "software", "data", "machine", "learning", "full", "stack", "web", "email", "phone", "mobile",
    "personal", "details", "career", "technical", "professional", "page", "of", "and", "the",
}
NAME_TOKEN_RE = re.compile(r"^[A-Za-z][A-Za-z.'\-]*$")


def extract_name(text: str, filename: str) -> str:
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()][:8]
    for line in lines:
        if "@" in line or re.search(r"\d|http|www\.", line, re.I):
            continue
        words = line.replace(",", " ").split()
        if not 2 <= len(words) <= 4:
            continue
        if not all(NAME_TOKEN_RE.match(w) for w in words):
            continue
        if any(w.lower().strip(".") in NAME_BLOCKLIST for w in words):
            continue
        return " ".join(w.capitalize() if w.isupper() or w.islower() else w for w in words)
    stem = re.sub(r"\.[A-Za-z0-9]+$", "", filename)
    stem = re.sub(r"[_\-.\d]+", " ", stem)
    stem = re.sub(r"(?i)\b(resume|cv|curriculum|vitae)\b", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem.title() if stem else "Unknown"


MONTH_NUM = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
_TOKEN = (
    r"(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s*(?:19|20)\d{2}"
    r"|(?:0?[1-9]|1[0-2])[/.](?:19|20)\d{2}"
    r"|(?:19|20)\d{2})"
)
_END = rf"(?:{_TOKEN}|present|currently|current|till date|to date|ongoing|now|today)"
RANGE_RE = re.compile(rf"({_TOKEN})\s*(?:-|–|—|\bto\b|\buntil\b|\btill\b)\s*({_END})", re.I)

EXP_HEADINGS = {
    "experience", "work experience", "professional experience", "employment", "employment history",
    "work history", "internships", "internship", "career history", "professional background",
    "relevant experience", "industrial experience", "internship experience",
}
OTHER_HEADINGS = {
    "education", "academic background", "academic qualifications", "qualifications", "education and training",
    "skills", "technical skills", "key skills", "core competencies", "projects", "academic projects",
    "personal projects", "certifications", "certificates", "achievements", "awards", "summary",
    "professional summary", "objective", "career objective", "profile", "languages", "interests",
    "hobbies", "publications", "references", "personal details", "declaration", "extracurricular activities",
    "courses", "training", "volunteering",
}
EDU_LINE_RE = re.compile(
    r"\b(b\.?\s?tech|m\.?\s?tech|b\.?\s?e\.?|b\.?\s?sc|m\.?\s?sc|bca|mca|bachelor|master|mba|ph\.?d|diploma|"
    r"university|college|school|cgpa|gpa|hsc|ssc|graduation|class\s+(?:x|xii|10|12))\b",
    re.I,
)


def _heading(line: str) -> Optional[str]:
    cleaned = re.sub(r"[^a-z ]", " ", line.lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned or len(line) > 45:
        return None
    if cleaned in EXP_HEADINGS:
        return "experience"
    if cleaned in OTHER_HEADINGS:
        return "other"
    return None


def _month_index(token: str, is_end: bool, today: date) -> Optional[tuple[int, bool]]:
    t = token.strip().lower()
    if re.fullmatch(r"present|currently|current|till date|to date|ongoing|now|today", t):
        return today.year * 12 + today.month, True
    m = re.match(r"([a-z]{3})[a-z]*\.?,?\s*((?:19|20)\d{2})$", t)
    if m:
        return int(m.group(2)) * 12 + MONTH_NUM[m.group(1)], True
    m = re.match(r"(\d{1,2})[/.]((?:19|20)\d{2})$", t)
    if m:
        return int(m.group(2)) * 12 + int(m.group(1)), True
    m = re.match(r"((?:19|20)\d{2})$", t)
    if m:
        return int(m.group(1)) * 12 + 1, False
    return None


def _employment_intervals(text: str, today: date) -> list[tuple[int, int]]:
    lines = text.split("\n")
    has_exp_heading = any(_heading(ln) == "experience" for ln in lines)
    section = None
    intervals: list[tuple[int, int]] = []
    now_idx = today.year * 12 + today.month
    for line in lines:
        head = _heading(line)
        if head:
            section = head
            continue
        if has_exp_heading and section != "experience":
            continue
        if section == "other" or EDU_LINE_RE.search(line):
            continue
        for m in RANGE_RE.finditer(line):
            start = _month_index(m.group(1), False, today)
            end = _month_index(m.group(2), True, today)
            if not start or not end:
                continue
            s, e = start[0], min(end[0], now_idx)
            if s < 1970 * 12 or s > now_idx or e < s:
                continue
            if e == s and start[1] and end[1]:
                e = s + 1
            if e - s > 50 * 12 or e == s:
                continue
            intervals.append((s, e))
    return intervals


def _merge_months(intervals: list[tuple[int, int]]) -> int:
    total, cur_s, cur_e = 0, None, None
    for s, e in sorted(intervals):
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                total += cur_e - cur_s
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        total += cur_e - cur_s
    return total


_NUM = r"(\d+(?:\.\d+)?)"
STATED_A = re.compile(
    rf"{_NUM}\s*(?:\+|(?:-|–|to)\s*\d+(?:\.\d+)?\+?)?\s*(years?|yrs?|months?)\s*(?:of\s+)?(?:[a-z\-]+\s+){{0,3}}?(?:experience|exp)\b",
    re.I,
)
STATED_B = re.compile(rf"experience\s*(?:of|:|-|for)?\s*{_NUM}\s*\+?\s*(years?|yrs?|months?)\b", re.I)


def _stated_values(text: str) -> list[int]:
    values = []
    for rx in (STATED_A, STATED_B):
        for m in rx.finditer(text):
            amount = float(m.group(1))
            unit = m.group(2).lower()
            months = round(amount * (1 if unit.startswith("month") else 12))
            if 0 < months <= 45 * 12:
                values.append(months)
    return values


def format_months(months: Optional[int]) -> str:
    if months is None:
        return "Not stated"
    if months < 12:
        return f"{months} month{'s' if months != 1 else ''}"
    years = round(months / 12, 1)
    years_txt = f"{years:g}"
    return f"{years_txt} yr" if years == 1 else f"{years_txt} yrs"


def extract_experience(text: str, today: Optional[date] = None) -> ExperienceInfo:
    today = today or date.today()
    dated = _merge_months(_employment_intervals(text, today))
    stated = max(_stated_values(text), default=0)
    if dated <= 0 and stated <= 0:
        return ExperienceInfo()
    if dated >= stated:
        return ExperienceInfo(months=dated, label=format_months(dated), source="dates")
    return ExperienceInfo(months=stated, label=format_months(stated), source="stated")


def extract_required_months(job_description: str) -> Optional[int]:
    for line in job_description.split("\n"):
        if not re.search(r"experience|exp\b", line, re.I):
            continue
        values = _stated_values(line)
        if values:
            return values[0]
        m = re.search(rf"{_NUM}\s*(?:\+|(?:-|–|to)\s*\d+(?:\.\d+)?\+?)?\s*(years?|yrs?)", line, re.I)
        if m:
            return round(float(m.group(1)) * 12)
    return None
