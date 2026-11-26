from api.documents.domain.document import Document, SourceRefId
from api.documents.domain.store import DocumentStore


class DocumentService:
    def __init__(self, store: DocumentStore) -> None:
        self.store = store

    async def get(self, raw_id: str) -> Document:
        source_ref_id = SourceRefId.create(raw_id)              # 형식 검증은 도메인 (R3)
        markdown = await self.store.get(source_ref_id.value)
        return Document(source_ref_id=source_ref_id, markdown=markdown)
