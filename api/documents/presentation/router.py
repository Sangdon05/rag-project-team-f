"""GET /api/v1/documents/{source_ref_id}."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from api.documents.application.service import DocumentService
from api.documents.presentation.dependencies import provide_document_service
from api.documents.presentation.schemas import DocumentData
from api.shared.responses import ErrorResponse, SuccessResponse

router = APIRouter(prefix="/api/v1", tags=["documents"])


@router.get(
    "/documents/{source_ref_id}",
    response_model=SuccessResponse[DocumentData],
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        405: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def get_document(
    source_ref_id: Annotated[str, Path(description="chat sources[].source_ref_id 값. 허용 문자 [A-Za-z0-9_-]")],
    service: Annotated[DocumentService, Depends(provide_document_service)],
) -> SuccessResponse[DocumentData]:
    document = await service.get(source_ref_id)          # 형식 검증은 도메인이 한다
    return SuccessResponse(data=DocumentData.from_domain(document))
