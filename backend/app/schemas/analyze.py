from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    lat: float
    lng: float
    address: str | None = None
    user_id: str | None = None
    compare_year: int | None = None
    resolution_cm: int = 10
    include_raw_tiles: bool = True


class AsyncAnalyzeResponse(BaseModel):
    job_id: str
    status: str
    estimated_seconds: int = 60


class Finding(BaseModel):
    type: str
    severity: str  # "minor" | "moderate" | "severe"
    bbox: list[float] = Field(description="normalized [x0, y0, x1, y1], 0-1")
    tile_index: list[int]
    confidence: float


class TemporalComparison(BaseModel):
    previous_score: int | None
    score_delta: int | None
    change_summary: str


class ImageUrls(BaseModel):
    full: str | None = None
    masked: str | None = None
    tiles: list[str] = []


class AnalysisResult(BaseModel):
    building_id: str
    score: int
    condition: str  # "good" | "aging" | "poor"
    confidence: float
    resolution_cm: int
    footprint_masked: bool
    imagery_date: str | None
    findings: list[Finding]
    temporal: TemporalComparison | None
    image_urls: ImageUrls


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: float
    stage: str | None = None
    result: AnalysisResult | None = None
    error: str | None = None


class FeedbackRequest(BaseModel):
    job_id: str
    user_id: str | None = None
    corrected_score: int | None = None
    notes: str | None = None
    corrected_findings: list[Finding] | None = None
