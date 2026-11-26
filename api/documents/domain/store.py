from abc import ABC, abstractmethod


class DocumentStore(ABC):
    """문서 저장소 포트. 계약 원본은 docs/references/api-rag-integration.md 2절."""

    @abstractmethod
    async def get(self, source_ref_id: str) -> str:
        """원문 Markdown. 없으면 DocumentNotFoundError, 읽기 실패는 DocumentSourceError."""
