"""문서 도메인. 순수 파이썬 (R1)."""

import re
from dataclasses import dataclass

from api.documents.domain.exceptions import InvalidSourceRefIdError

# \w 대신 문자 클래스를 직접 써서 유니코드 문자·숫자를 받지 않는다.
_SOURCE_REF_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]+")


@dataclass(frozen=True)
class SourceRefId:
    """원문 Markdown 파일명(확장자 제외). 경로 탈출을 막는 유일한 방어선이다."""

    value: str

    @classmethod
    def create(cls, raw: str) -> "SourceRefId":
        """허용 문자 밖이 하나라도 있으면 InvalidSourceRefIdError. 변환(strip, 대소문자)하지 않는다."""
        # fullmatch라서 끝의 줄바꿈도 거부한다.
        if not isinstance(raw, str) or _SOURCE_REF_ID_PATTERN.fullmatch(raw) is None:
            raise InvalidSourceRefIdError()
        return cls(value=raw)


@dataclass(frozen=True)
class Document:
    """조회 결과. markdown은 받은 그대로(빈 문자열 허용, 가공 없음)."""

    source_ref_id: SourceRefId
    markdown: str
