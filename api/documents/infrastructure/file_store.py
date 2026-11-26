"""파일 시스템 문서 저장소. 읽기만 한다."""

import asyncio
import logging
import os
from pathlib import Path

from api.documents.domain.exceptions import DocumentNotFoundError, DocumentSourceError
from api.documents.domain.store import DocumentStore

logger = logging.getLogger(__name__)


class FileDocumentStore(DocumentStore):
    """`<base_dir>/<source_ref_id>_*.md`를 읽는다. source_ref_id는 검증된 도감번호 3자리만 받는다."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    def _find(self, source_ref_id: str) -> list[Path]:
        # Path.glob은 폴더 읽기 OSError를 삼켜 빈 결과(404)를 내므로 os.scandir로 OSError를 올린다.
        prefix = f"{source_ref_id}_"
        with os.scandir(self.base_dir) as entries:
            return sorted(
                Path(entry.path)
                for entry in entries
                if entry.name.startswith(prefix) and entry.name.endswith(".md")
            )

    async def get(self, source_ref_id: str) -> str:
        if not self.base_dir.is_dir():
            # 문서 폴더 설정 오류를 404로 숨기지 않는다.
            logger.warning("문서 폴더 없음 (source_ref_id=%s)", source_ref_id)
            raise DocumentSourceError()
        try:
            matches = await asyncio.to_thread(self._find, source_ref_id)
            if not matches:
                raise DocumentNotFoundError()
            if len(matches) > 1:
                logger.warning("같은 번호 문서가 %d개 (source_ref_id=%s)", len(matches), source_ref_id)
                raise DocumentSourceError()
            raw = await asyncio.to_thread(matches[0].read_bytes)
            return raw.decode("utf-8")       # read_text의 줄바꿈 변환을 피한다
        except FileNotFoundError as exc:
            raise DocumentNotFoundError() from exc
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("문서 읽기 실패: %s (source_ref_id=%s)", type(exc).__name__, source_ref_id)
            raise DocumentSourceError() from exc
