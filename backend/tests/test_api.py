import io
import math

from backend.app import config

from .conftest import JD, MID, STRONG, WEAK, make_docx, make_pdf, make_png, make_scanned_pdf


def post(client, files, jd=JD):
    payload = [("resumes", (name, io.BytesIO(data), ctype)) for name, data, ctype in files]
    return client.post("/api/screen", data={"job_description": jd}, files=payload)


PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["model_loaded"] is True


def test_docs_available(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_batch_ranking_and_bounds(client):
    files = [
        ("weak.pdf", make_pdf(WEAK), PDF),
        ("strong.docx", make_docx(STRONG), DOCX),
        ("mid.txt", MID.encode(), "text/plain"),
    ]
    r = post(client, files)
    assert r.status_code == 200
    body = r.json()
    assert body["summary"] == {"total": 3, "screened": 3, "failed": 0}
    cands = body["candidates"]
    assert [c["filename"] for c in cands] == ["strong.docx", "mid.txt", "weak.pdf"]
    for c in cands:
        assert 0 <= c["score"] <= 100 and math.isfinite(c["score"])
    strong = cands[0]
    assert strong["name"] == "Priya Sharma" and strong["email"] == "priya.sharma@gmail.com"
    assert {"Python", "Machine Learning", "SQL", "Power BI", "Pandas"} <= set(strong["matched_skills"])
    assert "scikit-learn" in strong["matched_skills"]
    assert cands[2]["missing_skills"] and cands[2]["experience"]["months"] == 12
    assert body["job"]["required_months"] == 36
    assert "Machine Learning" in body["job"]["skills"]


def test_score_independent_of_batch_and_order(client):
    alone = post(client, [("s.txt", STRONG.encode(), "text/plain")]).json()["candidates"][0]["score"]
    batch = post(client, [("w.txt", WEAK.encode(), "text/plain"), ("m.txt", MID.encode(), "text/plain"),
                          ("s.txt", STRONG.encode(), "text/plain")]).json()["candidates"]
    assert next(c for c in batch if c["filename"] == "s.txt")["score"] == alone
    again = post(client, [("s.txt", STRONG.encode(), "text/plain")]).json()["candidates"][0]["score"]
    assert again == alone


def test_partial_failures(client):
    files = [
        ("good.txt", STRONG.encode(), "text/plain"),
        ("empty.pdf", b"", PDF),
        ("fake.pdf", b"this is not a pdf at all, just text pretending", PDF),
        ("corrupt.pdf", b"%PDF-1.4\n garbage garbage garbage", PDF),
        ("run.exe", b"MZ\x90\x00", "application/octet-stream"),
        ("wrongtype.txt", STRONG.encode(), "image/png"),
        ("dup.txt", STRONG.encode(), "text/plain"),
        ("short.txt", b"hi", "text/plain"),
    ]
    body = post(client, files).json()
    assert body["summary"]["screened"] == 1 and body["summary"]["failed"] == 7
    errors = {f["filename"]: f["error"] for f in body["failed"]}
    assert "empty" in errors["empty.pdf"].lower()
    assert "not a valid" in errors["fake.pdf"]
    assert "Unsupported" in errors["run.exe"]
    assert "does not match" in errors["wrongtype.txt"]
    assert "Duplicate" in errors["dup.txt"]
    assert "corrupted" in errors["corrupt.pdf"].lower() or "processed" in errors["corrupt.pdf"].lower()


def test_size_limit(client, monkeypatch):
    monkeypatch.setattr("backend.app.extraction.MAX_FILE_MB", 0)
    body = post(client, [("a.txt", STRONG.encode(), "text/plain")]).json()
    assert body["summary"]["failed"] == 1 and "limit" in body["failed"][0]["error"]


def test_input_validation(client):
    assert post(client, [("a.txt", STRONG.encode(), "text/plain")], jd="  ").status_code == 422
    assert post(client, [("a.txt", STRONG.encode(), "text/plain")], jd="short").json()["error"]
    r = client.post("/api/screen", data={"job_description": JD})
    assert r.status_code == 422 and "error" in r.json()
    assert post(client, [("a.txt", b"x", "text/plain")], jd="x" * (config.MAX_JD_CHARS + 1)).status_code == 422


def test_resume_retrieval(client):
    pdf = make_pdf(STRONG)
    body = post(client, [("My Resume.pdf", pdf, PDF), ("b.docx", make_docx(MID), DOCX)]).json()
    by_name = {c["filename"]: c for c in body["candidates"]}
    r = client.get(f"/api/resumes/{by_name['My Resume.pdf']['resume_id']}")
    assert r.status_code == 200 and r.content == pdf and r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith("inline")
    docx_id = by_name['b.docx']['resume_id']
    view = client.get(f"/api/resumes/{docx_id}")
    assert view.headers["content-type"].startswith("text/html") and "Anita Rao" in view.text and "Gamma Ltd" in view.text
    assert f"/api/resumes/{docx_id}?download=true" in view.text
    original = client.get(f"/api/resumes/{docx_id}?download=true")
    assert original.headers["content-disposition"].startswith("attachment")
    assert client.get("/api/resumes/" + "0" * 32).status_code == 404
    assert client.get("/api/resumes/..%2F..%2Fetc%2Fpasswd").status_code == 404
    assert client.get("/api/resumes/not-an-id").json()["error"]


def test_ocr_image_and_scanned_pdf(client):
    text = "Meera Nair\nmeera.nair@gmail.com\n\nWork Experience\nData Scientist at Acme   Jan 2020 - Jan 2024\nPython machine learning SQL pandas power bi dashboards"
    png = post(client, [("scan.png", make_png(text), "image/png")]).json()
    spdf = post(client, [("scan.pdf", make_scanned_pdf(text), PDF)]).json()
    for body in (png, spdf):
        assert body["summary"]["screened"] == 1, body
        c = body["candidates"][0]
        assert c["ocr_used"] is True
        assert c["email"] == "meera.nair@gmail.com"
        assert "Python" in c["matched_skills"]
        assert c["experience"]["months"] == 48


def test_text_pdf_does_not_use_ocr(client):
    c = post(client, [("t.pdf", make_pdf(STRONG), PDF)]).json()["candidates"][0]
    assert c["ocr_used"] is False


def test_model_unavailable_returns_503(client):
    from backend.app import scoring

    saved = scoring._encoder
    scoring._encoder = None
    scoring._load_error = "boom"
    try:
        r = post(client, [("a.txt", STRONG.encode(), "text/plain")])
        assert r.status_code == 503 and "boom" in r.json()["error"]
    finally:
        scoring.set_encoder(saved)


def test_scoring_math():
    from backend.app.scoring import calibrate_similarity, combine_score

    assert calibrate_similarity(-1) == 0 and calibrate_similarity(2) == 1
    assert combine_score(1, 1, 1) == 100 and combine_score(0, 0, 0) == 0
    assert combine_score(1.0, None, None) == 100
    assert 0 <= combine_score(0.5, None, 0.2) <= 100


def test_zip_contains_exactly_selected(client):
    import zipfile

    files = [(f"cv{i}.txt", (STRONG if i == 0 else MID).replace("Anita", f"Anita{i}").replace("Priya", f"Priya{i}").encode() + f"\nref {i}".encode(), "text/plain") for i in range(4)]
    files.append(("cv0.txt", b"Different Person\nEmail x@y.com\n" + MID.encode(), "text/plain"))
    body = post(client, files).json()
    ranked = body["candidates"]
    assert len(ranked) == 5
    chosen = ranked[:3]
    r = client.post("/api/resumes/zip", json={"resume_ids": [c["resume_id"] for c in chosen]})
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert r.headers["x-missing-resumes"] == "0"
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = zf.namelist()
        assert len(names) == 3 and len(set(names)) == 3
        assert names[0].startswith("01_") and names[2].startswith("03_")
        assert zf.testzip() is None
        assert [n.split("_", 1)[1] for n in names] == [c["filename"] for c in chosen]


def test_zip_validation_and_missing(client):
    body = post(client, [("a.txt", STRONG.encode(), "text/plain")]).json()
    good = body["candidates"][0]["resume_id"]
    assert client.post("/api/resumes/zip", json={"resume_ids": []}).status_code == 422
    assert client.post("/api/resumes/zip", json={"resume_ids": ["../../etc/passwd"]}).status_code == 422
    assert client.post("/api/resumes/zip", json={"resume_ids": ["0" * 32]}).status_code == 404
    r = client.post("/api/resumes/zip", json={"resume_ids": [good, "f" * 32, good]})
    assert r.status_code == 200 and r.headers["x-missing-resumes"] == "1"
    import zipfile
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        assert len(zf.namelist()) == 1


def test_tesseract_env_config(monkeypatch):
    from backend.app import extraction

    monkeypatch.setattr(extraction, "TESSERACT_CMD", r"C:\does\not\exist\tesseract.exe")
    assert extraction.configure_tesseract() is False
    monkeypatch.setattr(extraction, "TESSERACT_CMD", None)
    assert extraction.configure_tesseract() is True
