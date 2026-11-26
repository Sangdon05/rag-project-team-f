from typing import Literal

from pydantic import BaseModel, Field

from api.chat.domain.answer import Answer, AnswerMode


class MessageIn(BaseModel):
    role: Literal["user", "assistant"] = Field(..., description="화자")
    content: str = Field(..., description="내용. 앞뒤 공백 제거 후 비어 있으면 안 된다. 길이 한도 없음")


class ChatRequest(BaseModel):
    messages: list[MessageIn] = Field(
        ..., description="대화 전체. 1개 이상 API_MAX_MESSAGES개 이하, user로 시작·끝, 교대"
    )

    def to_raw(self) -> list[tuple[str, str]]:
        return [(m.role, m.content) for m in self.messages]


class SourceOut(BaseModel):
    ref: int = Field(..., description="출처 번호. answer 안 [n]의 n")
    chunk_id: str = Field(..., description="청크 ID (RAG 메타데이터 그대로)")
    source_ref_id: str = Field(..., description="원문 Markdown 파일명(확장자 제외). documents 조회 키")


class EmbeddingOut(BaseModel):
    query_model: str = Field(..., min_length=1, max_length=200, description="이번 질의 임베딩에 실제 사용한 모델 ID")
    document_model: str = Field(..., min_length=1, max_length=200, description="현재 인덱스에 결합된 문서 임베딩 모델 ID")


class ChatData(BaseModel):
    answer: str = Field(..., description="답변. 비어 있지 않음")
    mode: AnswerMode = Field(..., description="생성 방식 mock | llm | rag")
    sources: list[SourceOut] = Field(..., description="출처. 생성기 순서·값 그대로. mock·llm은 []")
    embedding: EmbeddingOut | None = Field(
        default=None, description="RAG가 실제 사용 정보를 제공한 경우에만 포함. GPT 답변 모델이 아님"
    )

    @classmethod
    def from_domain(cls, answer: Answer) -> "ChatData":
        return cls(
            answer=answer.text,
            mode=answer.mode,
            sources=[
                SourceOut(ref=s.ref, chunk_id=s.chunk_id, source_ref_id=s.source_ref_id)
                for s in answer.sources
            ],
            embedding=(EmbeddingOut(
                query_model=answer.embedding.query_model,
                document_model=answer.embedding.document_model,
            ) if answer.embedding is not None else None),
        )
