"""GET /health. 외부 호출 없이 고정 값을 돌려준다."""

from fastapi import APIRouter

from api.health.presentation.schemas import HealthData
from api.shared.responses import ErrorResponse, SuccessResponse

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=SuccessResponse[HealthData],
    responses={405: {"model": ErrorResponse}},
)
async def health() -> SuccessResponse[HealthData]:
    return SuccessResponse(data=HealthData(status="ok"))
