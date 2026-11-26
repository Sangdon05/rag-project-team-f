from pydantic import BaseModel, Field

from api.documents.domain.document import Document


class DocumentData(BaseModel):
    source_ref_id: str = Field(..., description="요청한 문서 ID 그대로")
    markdown: str = Field(..., description="원문 Markdown 그대로 (HTML 변환 없음)")

    @classmethod
    def from_domain(cls, document: Document) -> "DocumentData":
        return cls(source_ref_id=document.source_ref_id.value, markdown=document.markdown)
