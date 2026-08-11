from pydantic import BaseModel


class IngestRequest(BaseModel):
    region_hint: str | None = None


class IngestResponse(BaseModel):
    storm_events_created: list[str]
    jobs_processed: int
