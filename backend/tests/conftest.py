import hashlib
import io
import re

import pymupdf as fitz
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont

from backend.app import scoring
from backend.app.main import app


def hashing_encoder(texts: list[str]) -> np.ndarray:
    out = np.zeros((len(texts), 256))
    for i, text in enumerate(texts):
        for word in re.findall(r"[a-z0-9+#.]+", text.lower()):
            out[i, int(hashlib.md5(word.encode()).hexdigest(), 16) % 256] += 1
    return out


@pytest.fixture(scope="session")
def client():
    scoring.set_encoder(hashing_encoder)
    with TestClient(app) as c:
        yield c
    scoring.set_encoder(None)


def make_pdf(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(40, 40, 560, 800), text, fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


def render_text_image(text: str) -> Image.Image:
    img = Image.new("RGB", (1400, 1800), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 34)
    except OSError:
        font = ImageFont.load_default()
    y = 40
    for line in text.split("\n"):
        draw.text((50, y), line, fill="black", font=font)
        y += 50
    return img


def make_png(text: str) -> bytes:
    buf = io.BytesIO()
    render_text_image(text).save(buf, "PNG")
    return buf.getvalue()


def make_scanned_pdf(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(page.rect, stream=make_png(text))
    data = doc.tobytes()
    doc.close()
    return data


def make_docx(text: str) -> bytes:
    import docx

    d = docx.Document()
    for line in text.split("\n"):
        d.add_paragraph(line)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


JD = (
    "We are hiring a Data Scientist with 3+ years of experience in Python, Machine Learning, SQL, "
    "Pandas, scikit-learn and Power BI. You will build ML models and dashboards."
)

STRONG = """Priya Sharma
priya.sharma@gmail.com | +91 98765 43210

Summary
Data scientist with strong Python and machine learning skills.

Professional Experience
Data Scientist, Acme Analytics            Jan 2019 - Dec 2022
Built machine learning models using Python, Pandas, scikit-learn and SQL. Created Power BI dashboards.
Senior Data Scientist, Beta Corp          Jan 2022 - Present
Led ML projects with Python and SQL.

Education
B.Tech in Computer Science, Anna University 2014 - 2018
"""

WEAK = """Ramesh Kumar
ramesh.k@yahoo.com

Experience
Front Desk Associate, Hotel Sunrise     2023 - 2024
Welcomed guests, handled bookings and reception duties with good communication and teamwork.

Education
Bachelor of Commerce, City College 2019 - 2022
"""

MID = """Anita Rao
anita.rao@outlook.com

Work Experience
Analyst, Gamma Ltd    Mar 2021 - Mar 2023
Prepared reports with SQL and Excel, some Python scripting and Power BI dashboards.
"""
