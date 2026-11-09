from datetime import date

from backend.app.features import extract_email, extract_experience, extract_name, extract_required_months
from backend.app.skills import find_skills

from .conftest import STRONG, WEAK

TODAY = date(2026, 11, 4)


def test_email_extraction():
    assert extract_email("Contact: John.Doe+cv@Example-Mail.co.in.") == "john.doe+cv@example-mail.co.in"
    assert extract_email("no email here") is None
    assert extract_email("a@b") is None
    assert extract_email("noreply@corp.com then real.person@corp.com") == "real.person@corp.com"
    assert extract_email("bad..dots@x.com") is None


def test_name_extraction():
    assert extract_name(STRONG, "x.pdf") == "Priya Sharma"
    assert extract_name("Data Scientist\nphone 123", "ravi_kumar_resume.pdf") == "Ravi Kumar"


def test_experience_dates_ignore_education_and_merge_overlap():
    exp = extract_experience(STRONG, TODAY)
    assert exp.source == "dates"
    assert exp.months == (2026 * 12 + 11) - (2019 * 12 + 1)


def test_experience_not_confused_by_graduation_or_phone():
    exp = extract_experience(WEAK, TODAY)
    assert exp.months == 12 and exp.source == "dates"
    text = "Jane Roe\nPhone 2019 2020 55\nEducation\nB.Tech 2016 - 2020\nSkills\nPython"
    info = extract_experience(text, TODAY)
    assert info.months is None and info.label == "Not stated"


def test_experience_stated():
    assert extract_experience("I have 5+ years of professional experience in IT", TODAY).months == 60
    assert extract_experience("6 months of internship experience", TODAY).months == 6
    assert extract_experience("Project duration: 8 months", TODAY).months is None
    assert extract_required_months("Need 3+ years of experience in Python") == 36
    assert extract_required_months("Python, SQL") is None


def test_skills_no_ordinary_words():
    skills = find_skills("Good team work, project experience, communication. Java and JavaScript, ReactJS, Node.js, ML")
    assert {"Java", "JavaScript", "React", "Node.js", "Machine Learning"} <= skills
    assert not skills & {"Project Management", "Agile"}
    assert "Java" not in find_skills("expert in javascript only")
    assert find_skills("c++ and c# developer") >= {"C++", "C#"}
    assert "React" not in find_skills("frontend with jquery and bootstrap, reactive design")
