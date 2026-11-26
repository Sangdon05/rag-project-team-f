from api.documents.application.service import DocumentService


def provide_document_service() -> DocumentService:
    """Depends 플레이스홀더. api/container.py의 wire_dependencies가 연결한다."""
    raise NotImplementedError("DocumentService 의존성이 연결되지 않았습니다.")
