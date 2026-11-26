"""파일 시스템 문서 저장소. 읽기만 한다."""

import asyncio
import logging
from pathlib import Path

from api.documents.domain.exceptions import DocumentNotFoundError, DocumentSourceError
from api.documents.domain.store import DocumentStore

logger = logging.getLogger(__name__)


class FileDocumentStore(DocumentStore):
    """`<base_dir>/<source_ref_id>.md`를 읽는다. source_ref_id는 검증된 값만 받는다."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    async def get(self, source_ref_id: str) -> str:
        if not self.base_dir.is_dir():
            # 문서 폴더 설정 오류를 404로 숨기지 않는다.
            logger.warning("문서 폴더 없음 (source_ref_id=%s)", source_ref_id)
            raise DocumentSourceError()
        path = self.base_dir / f"{source_ref_id}.md"
        try:
            raw = await asyncio.to_thread(path.read_bytes)
            return raw.decode("utf-8")       # read_text의 줄바꿈 변환을 피한다
        except FileNotFoundError as exc:
            raise DocumentNotFoundError() from exc
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("문서 읽기 실패: %s (source_ref_id=%s)", type(exc).__name__, source_ref_id)
            raise DocumentSourceError() from exc
