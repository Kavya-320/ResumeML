import asyncio
import hashlib
import logging
import re
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import APIRouter, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import config, scoring
from .extraction import MEDIA_TYPES, ResumeError, docx_to_html, extract_text, ocr_available, safe_filename, validate_upload
from .schemas import Candidate, FailedResume, HealthResponse, JobInfo, ScreenResponse, ScreenSummary, ZipRequest
from .storage import store

logger = logging.getLogger("resumeml")
RESUME_ID_RE = re.compile(r"^[a-f0-9]{32}$")
INLINE_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".txt"}


async def _cleanup_loop() -> None:
    while True:
        await asyncio.sleep(300)
        await run_in_threadpool(store.purge_expired)


@asynccontextmanager
async def lifespan(_: FastAPI):
    async def warm_up() -> None:
        try:
            await run_in_threadpool(scoring.load_model)
            logger.info("Model ready: %s", config.MODEL_NAME)
        except Exception:
            logger.exception("Model failed to load")

    tasks = [asyncio.create_task(warm_up()), asyncio.create_task(_cleanup_loop())]
    yield
    for task in tasks:
        task.cancel()


app = FastAPI(title="ResumeML API", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Missing-Resumes"],
)


@app.exception_handler(StarletteHTTPException)
async def http_error(_: Request, exc: StarletteHTTPException):
    return JSONResponse({"error": str(exc.detail)}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    fields = ", ".join(str(e["loc"][-1]) for e in exc.errors())
    return JSONResponse({"error": f"Invalid or missing request fields: {fields}."}, status_code=422)


@app.exception_handler(Exception)
async def unexpected_error(_: Request, exc: Exception):
    logger.exception("Unhandled error", exc_info=exc)
    return JSONResponse({"error": "An unexpected server error occurred."}, status_code=500)


api = APIRouter(prefix="/api")


@api.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        model_loaded=scoring.model_loaded(),
        model_name=config.MODEL_NAME,
        ocr_available=await run_in_threadpool(ocr_available),
    )


async def _ensure_model() -> None:
    for _ in range(600):
        if scoring.model_loaded():
            return
        if scoring.load_error():
            break
        await asyncio.sleep(0.5)
    raise HTTPException(503, scoring.load_error() or "The ML model is still loading. Try again shortly.")


def _process(data: bytes, name: str, ext: str, ctype: Optional[str], job: scoring.JobContext) -> Candidate:
    extracted = extract_text(data, ext)
    stored = store.save(data, ext, name, MEDIA_TYPES[ext])
    try:
        return scoring.score_resume(job, extracted.text, stored.resume_id, name, extracted.ocr_used)
    except Exception:
        store.discard(stored.resume_id)
        raise


@api.post("/screen", response_model=ScreenResponse)
async def screen(job_description: str = Form(...), resumes: list[UploadFile] = File(...)) -> ScreenResponse:
    jd = job_description.strip()
    if len(jd) < config.MIN_JD_CHARS:
        raise HTTPException(422, f"Job description must be at least {config.MIN_JD_CHARS} characters.")
    if len(jd) > config.MAX_JD_CHARS:
        raise HTTPException(422, f"Job description must be at most {config.MAX_JD_CHARS} characters.")
    if not resumes:
        raise HTTPException(422, "Upload at least one resume.")
    if len(resumes) > config.MAX_FILES:
        raise HTTPException(413, f"A maximum of {config.MAX_FILES} resumes can be screened at once.")

    await _ensure_model()
    job = await run_in_threadpool(scoring.build_job, jd)

    limit = config.MAX_FILE_MB * 1024 * 1024
    seen: dict[str, str] = {}
    semaphore = asyncio.Semaphore(2)

    async def handle(upload: UploadFile) -> Candidate | FailedResume:
        name = safe_filename(upload.filename)
        try:
            data = await upload.read(limit + 1)
            ext = validate_upload(name, upload.content_type, data)
            digest = hashlib.sha256(data).hexdigest()
            if digest in seen:
                raise ResumeError(f"Duplicate of '{seen[digest]}'.")
            seen[digest] = name
            async with semaphore:
                return await run_in_threadpool(_process, data, name, ext, upload.content_type, job)
        except ResumeError as exc:
            return FailedResume(filename=name, error=str(exc))
        except Exception:
            logger.exception("Failed to screen %s", name)
            return FailedResume(filename=name, error="Unexpected error while processing this resume.")
        finally:
            await upload.close()

    results = await asyncio.gather(*(handle(u) for u in resumes))
    candidates = [r for r in results if isinstance(r, Candidate)]
    failed = [r for r in results if isinstance(r, FailedResume)]
    candidates.sort(key=lambda c: (-c.score, c.name.lower(), c.filename.lower()))

    return ScreenResponse(
        candidates=candidates,
        failed=failed,
        summary=ScreenSummary(total=len(resumes), screened=len(candidates), failed=len(failed)),
        job=JobInfo(skills=sorted(job.skills, key=str.lower), required_months=job.required_months),
    )


@api.post("/resumes/zip")
async def zip_resumes(body: ZipRequest):
    ids = list(dict.fromkeys(body.resume_ids))
    if any(not RESUME_ID_RE.match(i) for i in ids):
        raise HTTPException(422, "Invalid resume identifier.")
    found = [item for item in (store.get(i) for i in ids) if item is not None]
    if not found:
        raise HTTPException(404, "The selected resumes are no longer available. Screen them again to download them.")
    path = await run_in_threadpool(store.build_zip, found)
    return FileResponse(
        path,
        media_type="application/zip",
        filename="resumeml_selected_resumes.zip",
        headers={"X-Missing-Resumes": str(len(ids) - len(found))},
        background=BackgroundTask(path.unlink, missing_ok=True),
    )


@api.get("/resumes/{resume_id}")
async def get_resume(resume_id: str, download: bool = False):
    if not RESUME_ID_RE.match(resume_id):
        raise HTTPException(404, "Resume not found.")
    item = store.get(resume_id)
    if item is None:
        raise HTTPException(404, "This resume is no longer available. Screen it again to view it.")
    if item.path.suffix == ".docx" and not download:
        try:
            page = await run_in_threadpool(
                docx_to_html, item.path.read_bytes(), item.original_name, f"/api/resumes/{resume_id}?download=true"
            )
        except ResumeError as exc:
            raise HTTPException(422, str(exc))
        return HTMLResponse(
            page,
            headers={"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'", "X-Content-Type-Options": "nosniff"},
        )
    disposition = "inline" if item.path.suffix in INLINE_EXTS and not download else "attachment"
    return FileResponse(
        item.path,
        media_type=item.media_type,
        filename=item.original_name,
        content_disposition_type=disposition,
        headers={"X-Content-Type-Options": "nosniff"},
    )


app.include_router(api)
if config.FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=config.FRONTEND_DIR, html=True), name="frontend")
