import math
import threading
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

from . import config
from .features import extract_email, extract_experience, extract_name, extract_required_months
from .schemas import Candidate, ExperienceInfo, ScoreBreakdown
from .skills import compare_skills, find_skills

Encoder = Callable[[list[str]], np.ndarray]

_encoder: Optional[Encoder] = None
_load_error: Optional[str] = None
_lock = threading.Lock()

CHUNK_WORDS = 180
CHUNK_OVERLAP = 30
MAX_CHUNKS = 16


def set_encoder(encoder: Optional[Encoder]) -> None:
    global _encoder, _load_error
    with _lock:
        _encoder = encoder
        _load_error = None


def model_loaded() -> bool:
    return _encoder is not None


def load_error() -> Optional[str]:
    return _load_error


def load_model() -> None:
    global _encoder, _load_error
    with _lock:
        if _encoder is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(config.MODEL_NAME, cache_folder=config.MODEL_CACHE_DIR)
        except Exception as exc:
            _load_error = f"Could not load model '{config.MODEL_NAME}': {exc}"
            raise

        def encode(texts: list[str]) -> np.ndarray:
            return model.encode(texts, batch_size=32, show_progress_bar=False, convert_to_numpy=True)

        _encoder = encode
        _load_error = None


def embed(texts: list[str]) -> np.ndarray:
    if _encoder is None:
        raise RuntimeError(_load_error or "Model is not loaded.")
    vectors = np.asarray(_encoder(texts), dtype=np.float64)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.where(norms == 0, 1.0, norms)


def chunk_text(text: str, size: int = CHUNK_WORDS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    words = text.split()
    if not words:
        return []
    step = size - overlap
    chunks = [" ".join(words[i:i + size]) for i in range(0, len(words), step)]
    if len(chunks) > 1 and len(chunks[-1].split()) <= overlap:
        chunks.pop()
    return chunks[:MAX_CHUNKS]


def calibrate_similarity(cosine: float) -> float:
    span = config.SEMANTIC_CEIL - config.SEMANTIC_FLOOR
    return float(min(1.0, max(0.0, (cosine - config.SEMANTIC_FLOOR) / span)))


def combine_score(semantic: float, skills: Optional[float], experience: Optional[float]) -> float:
    parts = {"semantic": semantic, "skills": skills, "experience": experience}
    total_weight = sum(config.WEIGHTS[k] for k, v in parts.items() if v is not None)
    weighted = sum(config.WEIGHTS[k] * v for k, v in parts.items() if v is not None)
    score = 100.0 * weighted / total_weight
    if not math.isfinite(score):
        return 0.0
    return round(min(100.0, max(0.0, score)), 1)


def status_for(score: float) -> str:
    if score >= config.STRONG_THRESHOLD:
        return "strong"
    if score >= config.POSSIBLE_THRESHOLD:
        return "possible"
    return "weak"


@dataclass
class JobContext:
    text: str
    chunks: list[str]
    vectors: np.ndarray
    skills: set[str]
    required_months: Optional[int]


def build_job(job_description: str) -> JobContext:
    chunks = chunk_text(job_description)
    return JobContext(
        text=job_description,
        chunks=chunks,
        vectors=embed(chunks),
        skills=find_skills(job_description),
        required_months=extract_required_months(job_description),
    )


def semantic_similarity(job: JobContext, resume_vectors: np.ndarray) -> float:
    sims = job.vectors @ resume_vectors.T
    return float(np.clip(sims.max(axis=1).mean(), -1.0, 1.0))


def score_resume(job: JobContext, text: str, resume_id: str, filename: str, ocr_used: bool) -> Candidate:
    resume_vectors = embed(chunk_text(text))
    cosine = semantic_similarity(job, resume_vectors)
    semantic = calibrate_similarity(cosine)

    resume_skills = find_skills(text)
    matched, missing, other = compare_skills(job.skills, resume_skills)
    skill_cov = len(matched) / len(job.skills) if job.skills else None

    experience: ExperienceInfo = extract_experience(text)
    exp_fit = None
    if job.required_months and experience.months is not None:
        exp_fit = min(1.0, experience.months / job.required_months)

    score = combine_score(semantic, skill_cov, exp_fit)
    return Candidate(
        resume_id=resume_id,
        filename=filename,
        name=extract_name(text, filename),
        email=extract_email(text),
        experience=experience,
        score=score,
        semantic_similarity=round(cosine, 4),
        skill_match_percent=round(skill_cov * 100, 1) if skill_cov is not None else None,
        matched_skills=matched,
        missing_skills=missing,
        other_skills=other,
        breakdown=ScoreBreakdown(
            semantic=round(semantic * 100, 1),
            skills=round(skill_cov * 100, 1) if skill_cov is not None else None,
            experience=round(exp_fit * 100, 1) if exp_fit is not None else None,
        ),
        status=status_for(score),
        ocr_used=ocr_used,
    )
