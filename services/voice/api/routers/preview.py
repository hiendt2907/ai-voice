from fastapi import APIRouter
from pydantic import BaseModel
from tts.prosody import beats_to_chunks, ProsodyChunk

router = APIRouter(prefix="/preview", tags=["preview"])


class PreviewRequest(BaseModel):
    beats: list[dict]


class PreviewResponse(BaseModel):
    chunks: list[ProsodyChunk]
    total_duration_ms: int


@router.post("", response_model=PreviewResponse)
async def preview_script(req: PreviewRequest):
    chunks = beats_to_chunks(req.beats)
    total_ms = sum(c.pause_after_ms for c in chunks)
    return PreviewResponse(chunks=chunks, total_duration_ms=total_ms)
