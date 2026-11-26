"""POST /api/v1/chat."""

from typing import Annotated

from fastapi import APIRouter, Depends

from api.chat.application.service import AskService
from api.chat.presentation.dependencies import provide_ask_service
from api.chat.presentation.schemas import ChatData, ChatRequest
from api.shared.responses import ErrorResponse, SuccessResponse

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post(
    "/chat",
    response_model=SuccessResponse[ChatData],
    response_model_exclude_none=True,
    responses={
        400: {"model": ErrorResponse},
        405: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def chat(
    body: ChatRequest,
    service: Annotated[AskService, Depends(provide_ask_service)],
) -> SuccessResponse[ChatData]:
    answer = await service.ask(body.to_raw())
    return SuccessResponse(data=ChatData.from_domain(answer))
