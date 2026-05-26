from datetime import datetime, UTC
from fastapi import APIRouter
from ..config import Settings

router = APIRouter(tags=["health"])
settings = Settings()


@router.get("/health")
async def health_check():
    cloudfone_configured = bool(settings.cloudfone_ws_url and settings.cloudfone_auth_key)
    return {
        "status": "ok",
        "timestamp": datetime.now(UTC).isoformat(),
        "cloudfone": {
            "configured": cloudfone_configured,
            "ws_url": settings.cloudfone_ws_url or None,
            "service_name": settings.cloudfone_service_name or None,
        },
    }
