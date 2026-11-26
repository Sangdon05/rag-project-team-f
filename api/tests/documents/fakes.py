"""documents 테스트용 fake 저장소."""

from api.documents.domain.store import DocumentStore


class FakeDocumentStore(DocumentStore):
    def __init__(self, markdown: str = "fake", error: Exception | None = None) -> None:
        self.markdown = markdown
        self.error = error
        self.calls: list[str] = []

    async def get(self, source_ref_id: str) -> str:
        self.calls.append(source_ref_id)
        if self.error is not None:
            raise self.error
        return self.markdown
