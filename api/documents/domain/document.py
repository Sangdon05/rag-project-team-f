"""문서 도메인. 순수 파이썬 (R1)."""

import re
from dataclasses import dataclass

from api.documents.domain.exceptions import InvalidSourceRefIdError

# \d 대신 [0-9]를 써서 유니코드 숫자(아랍 숫자 등)를 받지 않는다.
_SOURCE_REF_ID_PATTERN = re.compile(r"[0-9]{3}")


@dataclass(frozen=True)
class SourceRefId:
    """도감번호 3자리(예: 001). 경로 탈출을 막는 유일한 방어선이다."""

    value: str

    @classmethod
    def create(cls, raw: str) -> "SourceRefId":
        """[0-9]{3}이 아니면 InvalidSourceRefIdError. 변환(0 채우기, strip)하지 않는다."""
        # fullmatch라서 끝의 줄바꿈도 거부한다.
        if not isinstance(raw, str) or _SOURCE_REF_ID_PATTERN.fullmatch(raw) is None:
            raise InvalidSourceRefIdError()
        return cls(value=raw)


@dataclass(frozen=True)
class Document:
    """조회 결과. markdown은 받은 그대로(빈 문자열 허용, 가공 없음)."""

    source_ref_id: SourceRefId
    markdown: str
