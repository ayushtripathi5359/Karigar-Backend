from fastapi import APIRouter

router = APIRouter(prefix="/v1/pricing", tags=["pricing"])

# Calculator logic moved to the dedicated calculator service (port 8010).
# All endpoints now live at /v1/calculator/.
