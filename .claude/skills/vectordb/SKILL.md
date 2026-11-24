---
name: vectordb
description: Use when building, syncing, or checking the vector index (embedding, Chroma collections, incremental re-embedding, index_version).
---

# vectordb

청크를 임베딩해 컬렉션에 저장하고, 데이터가 바뀌면 바뀐 청크만 다시 임베딩한다.

## 선택 사항

- 저장소: Chroma (persistent, `vectorstore/`)
- 임베딩: 한국어 지원 필수. 후보 `text-embedding-3-small`, `bge-m3` [미정]
- 컬렉션 이름 = `index_version` = `v{n}-{임베딩 약칭}-{템플릿 버전}` (예: `v1-te3s-tpl1`)

## 전체 빌드 vs 증분 sync

| 상황 | 방식 |
| --- | --- |
| 최초 빌드, 임베딩 모델 변경, 청크 템플릿 변경 | 새 컬렉션에 전체 빌드 |
| 데이터 일부 변경/추가/삭제 | 같은 컬렉션에 증분 sync |

## 증분 sync 절차

청크마다 메타데이터에 해시 2개를 저장한다.

- `content_hash = sha256(embed_model + "|" + text)` → 바뀌면 재임베딩
- `meta_hash = sha256(정렬된 메타데이터)` → 텍스트가 같고 이것만 바뀌면 메타데이터만 갱신

1. `collection.get(include=["metadatas"])`로 저장된 해시를 읽는다.
2. 새 chunks.jsonl과 비교해 분류한다.

   | 조건 | 처리 | 임베딩 |
   | --- | --- | --- |
   | 신규 또는 content_hash 다름 | `upsert` | O |
   | content_hash 같음, meta_hash 다름 | `update(metadatas=...)` | X |
   | 새 목록에 없음 | `delete` | X |
   | 둘 다 같음 | 건너뜀 | X |

3. embedded / meta_only / deleted / unchanged 건수를 `runs/manifest.jsonl`에 기록한다. 변경 없는 데이터를 임베딩하지 않았다는 증거다.

참고 시뮬레이션(151마리 × 3섹션, 가짜 임베딩): 피카츄 speed만 변경 → 임베딩 1건, 유지 452건. 변경 없이 재실행 → 임베딩 0건. 메타데이터만 변경 → 임베딩 0건, meta_only 3건.

## 주의

- 청크 텍스트가 비결정적이면(시각, 순서, 숫자 포맷) 데이터가 그대로여도 전체가 재임베딩된다.
- 임베딩 모델명이 content_hash에 들어 있으므로 모델 변경은 증분 sync가 아니라 새 컬렉션으로 처리한다.
- 조건이 좁은 필터는 결과가 k보다 적을 수 있다. 검색 툴은 결과 개수를 함께 반환한다.
- 정렬·top-N·집계는 where 절로 풀 수 없다. 정규화 데이터를 직접 조회하는 툴의 몫이다.

## 검증

- 컬렉션 청크 수 = chunks.jsonl 청크 수, 누락 ID 0
- smoke test: 151마리, 165개 기술 이름으로 검색 시 해당 id가 top-1
- 변경 없이 sync 재실행 시 embedded = 0
