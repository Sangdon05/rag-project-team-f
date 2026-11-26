/** Per-answer embedding metadata presentation. Never selects or calls a model. */
const MODEL_FIELDS = ['query_model', 'document_model'];
const CONTROL = /\p{C}/u;
const UNKNOWN_LABEL = '임베딩 모델 정보 없음';

export function normalizeEmbedding(value) {
  if (value == null) return null;
  if (typeof value !== 'object' || Array.isArray(value)
      || Object.keys(value).length !== MODEL_FIELDS.length
      || !MODEL_FIELDS.every(field => Object.hasOwn(value, field))) {
    throw new TypeError('Invalid embedding model metadata.');
  }
  const normalized = {};
  for (const field of MODEL_FIELDS) {
    const model = value[field];
    if (typeof model !== 'string' || [...model].length > 200 || CONTROL.test(model) || !model.trim()) {
      throw new TypeError('Invalid embedding model metadata.');
    }
    normalized[field] = model.trim();
  }
  return normalized;
}

function familyOf(model) {
  const name = model.split('/').at(-1).toLowerCase();
  if (/^solar-embedding(?:-|$)/u.test(name)) return 'solar';
  if (/^text-embedding-/u.test(name)) return 'openai';
  if (/^kure(?:-|$)/u.test(name)) return 'kure';
  return 'unknown';
}

export function embeddingPresentation(value) {
  const embedding = normalizeEmbedding(value);
  if (!embedding) return { family: 'unknown', label: UNKNOWN_LABEL, title: UNKNOWN_LABEL };
  return {
    family: familyOf(embedding.query_model),
    label: embedding.query_model,
    title: `질의 임베딩: ${embedding.query_model} · 문서 임베딩: ${embedding.document_model}`,
  };
}

export function renderEmbeddingStatus(host, message) {
  host.replaceChildren();
  const document = host.ownerDocument;
  if (message?.mode !== 'rag') {
    host.textContent = message?.mode === 'llm'
      ? 'llm · 검색 근거를 보장하지 않는 생성 답변'
      : 'mock · 서버가 반환한 예시 답변';
    return;
  }
  host.append(document.createTextNode('rag · '));
  let presentation;
  try { presentation = embeddingPresentation(message.embedding); }
  catch { presentation = embeddingPresentation(null); }
  const detail = document.createElement('span');
  detail.className = 'nx-embedding-status';
  detail.setAttribute('title', presentation.title);
  detail.setAttribute('aria-label', presentation.title);
  const dot = document.createElement('span');
  dot.className = `nx-embedding-dot${presentation.family === 'unknown' ? '' : ' is-pulsing'}`;
  dot.setAttribute('data-family', presentation.family);
  dot.setAttribute('aria-hidden', 'true');
  const label = document.createElement('span');
  label.className = 'nx-embedding-label';
  label.textContent = presentation.label;
  detail.append(dot, label);
  host.append(detail);
}
