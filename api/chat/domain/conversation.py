"""대화 도메인. 순수 파이썬 (R1). 판정 순서는 chat 설계안 4.2."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from api.chat.domain.exceptions import InvalidConversationError
from api.shared.exceptions import ApiError

COUNT_MESSAGE = "메시지는 1개 이상 {max}개 이하여야 합니다."
ORDER_MESSAGE = "대화는 user로 시작하고 끝나야 하며 user와 assistant가 번갈아 와야 합니다."
EMPTY_CONTENT_MESSAGE = "메시지 내용이 비어 있습니다."


class Role(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


_ROLE_VALUES = frozenset(role.value for role in Role)


@dataclass(frozen=True)
class ConversationLimits:
    max_messages: int

    def __post_init__(self) -> None:
        if self.max_messages < 1:
            raise ApiError("max_messages는 1 이상이어야 합니다.")   # 설정 오류: 요청 입력이 아니므로 500 계열


@dataclass(frozen=True)
class Message:
    role: Role
    content: str

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise InvalidConversationError(EMPTY_CONTENT_MESSAGE)


@dataclass(frozen=True)
class Conversation:
    messages: tuple[Message, ...]

    @classmethod
    def create(cls, raw: Sequence[tuple[str, str]], limits: ConversationLimits) -> "Conversation":
        """개수 → 순서(role 포함) → 빈 content 순으로 검사한다. 먼저 걸린 하나만 올린다."""
        items = list(raw)
        if not 1 <= len(items) <= limits.max_messages:
            raise InvalidConversationError(COUNT_MESSAGE.format(max=limits.max_messages))
        for index, (role, _content) in enumerate(items):
            expected = Role.USER if index % 2 == 0 else Role.ASSISTANT
            if role not in _ROLE_VALUES or role != expected:
                raise InvalidConversationError(ORDER_MESSAGE)
        if items[-1][0] != Role.USER:
            raise InvalidConversationError(ORDER_MESSAGE)
        for _role, content in items:
            if not isinstance(content, str) or not content.strip():
                raise InvalidConversationError(EMPTY_CONTENT_MESSAGE)
        return cls(messages=tuple(Message(Role(role), content.strip()) for role, content in items))

    @property
    def question(self) -> str:
        """마지막 user 메시지."""
        return self.messages[-1].content

    @property
    def history(self) -> tuple[Message, ...]:
        """질문 앞의 대화."""
        return self.messages[:-1]
