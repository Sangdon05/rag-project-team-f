"""GET /api/v1/suggestion."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from api.shared.responses import ErrorResponse, SuccessResponse
from api.suggestion.application.service import SuggestionService
from api.suggestion.domain.suggestion import SuggestionLevel
from api.suggestion.presentation.dependencies import provide_suggestion_service
from api.suggestion.presentation.schemas import SuggestionData

router = APIRouter(prefix="/api/v1", tags=["suggestion"])


@router.get(
    "/suggestion",
    response_model=SuccessResponse[SuggestionData],
    responses={400: {"model": ErrorResponse}, 405: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def suggestion(
    service: Annotated[SuggestionService, Depends(provide_suggestion_service)],
    level: Annotated[SuggestionLevel, Query(description="사용자 등급. 대소문자 구분")] = SuggestionLevel.BEGINNER,
) -> SuccessResponse[SuggestionData]:
    suggestion_set = await service.suggest(level)
    return SuccessResponse(data=SuggestionData.from_domain(suggestion_set))
