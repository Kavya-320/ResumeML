import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

FRONTEND_DIR = BASE_DIR.parent.parent / "frontend"
SKILLS_FILE = BASE_DIR / "data" / "skills.json"

MODEL_NAME = os.getenv("MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")
MODEL_CACHE_DIR = os.getenv("MODEL_CACHE_DIR") or None

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", Path(tempfile.gettempdir()) / "resumeml_uploads"))
MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "10"))
MAX_FILES = int(os.getenv("MAX_FILES", "200"))
RESUME_TTL_MINUTES = int(os.getenv("RESUME_TTL_MINUTES", "120"))
MIN_JD_CHARS = 30
MAX_JD_CHARS = 20000
MIN_RESUME_CHARS = 40
OCR_MAX_PAGES = int(os.getenv("OCR_MAX_PAGES", "4"))
TESSERACT_CMD = os.getenv("TESSERACT_CMD") or None
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]

WEIGHTS = {"semantic": 0.55, "skills": 0.35, "experience": 0.10}
SEMANTIC_FLOOR = 0.15
SEMANTIC_CEIL = 0.65
STRONG_THRESHOLD = 65.0
POSSIBLE_THRESHOLD = 40.0
