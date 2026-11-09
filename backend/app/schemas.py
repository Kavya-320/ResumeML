from typing import Literal, Optional
from pydantic import BaseModel, Field

from .config import MAX_FILES


class ExperienceInfo(BaseModel):
    months: Optional[int] = None
    label: str = "Not stated"
    source: Literal["dates", "stated", "unavailable"] = "unavailable"


class ScoreBreakdown(BaseModel):
    semantic: float
    skills: Optional[float] = None
    experience: Optional[float] = None


class Candidate(BaseModel):
    resume_id: str
    filename: str
    name: str
    email: Optional[str] = None
    experience: ExperienceInfo
    score: float = Field(ge=0, le=100)
    semantic_similarity: float
    skill_match_percent: Optional[float] = None
    matched_skills: list[str]
    missing_skills: list[str]
    other_skills: list[str]
    breakdown: ScoreBreakdown
    status: Literal["strong", "possible", "weak"]
    ocr_used: bool = False


class FailedResume(BaseModel):
    filename: str
    error: str


class ScreenSummary(BaseModel):
    total: int
    screened: int
    failed: int


class JobInfo(BaseModel):
    skills: list[str]
    required_months: Optional[int] = None


class ScreenResponse(BaseModel):
    candidates: list[Candidate]
    failed: list[FailedResume]
    summary: ScreenSummary
    job: JobInfo


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    model_name: str
    ocr_available: bool


class ZipRequest(BaseModel):
    resume_ids: list[str] = Field(min_length=1, max_length=MAX_FILES)
