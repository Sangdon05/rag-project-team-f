/** Team HTTP contract. No local answers, persona fields, or synthetic sources. */
import { normalizeEmbedding } from './neo-embedding.mjs';
export class TeamApiError extends Error {
  constructor(kind, message, { httpStatus = null, code = null } = {}) {
    super(message);
    this.name = "TeamApiError";
    this.kind = kind;
    this.httpStatus = httpStatus;
    this.code = code;
  }
}

const nonempty = value => typeof value === "string" && value.trim().length > 0;
const failFormat = message => { throw new TeamApiError("format", message); };

/** Validate immediately before POST; return only the two supported fields. */
export function validateTeamMessages(messages, { maxMessages = 20, maxContentLength = null } = {}) {
  if (!Number.isInteger(maxMessages) || maxMessages < 1) throw new TeamApiError("config", "대화 개수 설정을 확인해 주세요.");
  if (maxContentLength !== null && (!Number.isInteger(maxContentLength) || maxContentLength < 1)) {
    throw new TeamApiError("config", "메시지 길이 설정을 확인해 주세요.");
  }
  if (!Array.isArray(messages) || !messages.length || messages.length > maxMessages || messages.length % 2 !== 1) {
    throw new TeamApiError("validation", "질문으로 시작하고 끝나는 대화 범위를 확인해 주세요.");
  }
  return messages.map((message, index) => {
    const expected = index % 2 === 0 ? "user" : "assistant";
    if (message?.role !== expected || typeof message.content !== "string") {
      throw new TeamApiError("validation", "대화는 질문과 답변 순서로 번갈아야 해요.");
    }
    const content = (expected === "assistant" ? message.content.replace(/\[\d+\]/g, "") : message.content).trim();
    if (!content || (maxContentLength !== null && Array.from(content).length > maxContentLength)) {
      throw new TeamApiError("validation", "메시지가 비어 있거나 서버의 길이 제한을 넘었어요.");
    }
    return { role: expected, content };
  });
}

function dataEnvelope(body) {
  if (!body || body.success !== true || !body.data || typeof body.data !== "object" || Array.isArray(body.data)) {
    failFormat("서버 응답의 success와 data 형식을 확인할 수 없어요.");
  }
  return body.data;
}

export function validateTeamAnswer(body) {
  const data = dataEnvelope(body);
  if (!nonempty(data.answer) || !["mock", "llm", "rag"].includes(data.mode) || !Array.isArray(data.sources)) {
    failFormat("답변, 생성 모드 또는 출처의 응답 형식이 올바르지 않아요.");
  }
  const refs = new Map();
  for (const row of data.sources) {
    if (!Number.isInteger(row?.ref) || row.ref < 1 || !nonempty(row.chunk_id) || !nonempty(row.source_ref_id)) {
      failFormat("출처의 번호와 문서 식별자를 확인할 수 없어요.");
    }
    const source = { ref: row.ref, chunk_id: row.chunk_id, source_ref_id: row.source_ref_id };
    const previous = refs.get(source.ref);
    if (previous && (previous.chunk_id !== source.chunk_id || previous.source_ref_id !== source.source_ref_id)) {
      failFormat("같은 출처 번호에 서로 다른 문서가 연결되어 있어요.");
    }
    refs.set(source.ref, source);
  }
  const result = { answer: data.answer, mode: data.mode, sources: [...refs.values()] };
  if (data.embedding != null) {
    if (data.mode !== 'rag') failFormat('검색하지 않은 답변에 임베딩 모델 정보가 포함됐어요.');
    try { result.embedding = normalizeEmbedding(data.embedding); }
    catch { failFormat('임베딩 모델 정보를 확인할 수 없어요.'); }
  }
  return result;
}

export function createTeamApiClient({ config = {}, fetchImpl = globalThis.fetch?.bind(globalThis) } = {}) {
  const paths = { suggestions: config.suggestionsPath, ask: config.askPath, document: config.documentPath };
  const missing = [!config.baseUrl && "API 주소", !paths.suggestions && "추천 질문 경로", !paths.ask && "질문 경로",
    !paths.document && "원문 문서 경로"].filter(Boolean);
  const documentCache = new Map();
  const maxMessages = config.maxMessages ?? 20;
  const maxContentLength = config.maxContentLength ?? null;

  function endpoint(kind, sourceRefId) {
    if (!config.baseUrl || !paths[kind]) throw new TeamApiError("config", "팀 API 주소와 경로가 아직 확인되지 않았어요.");
    let base, url;
    try {
      base = new URL(config.baseUrl);
      let path = paths[kind];
      if (kind === "document") {
        if (!nonempty(sourceRefId) || sourceRefId === "." || sourceRefId === "..") {
          throw new TeamApiError("validation", "문서 식별자가 올바르지 않아요.");
        }
        if (!path.includes("{source_ref_id}")) throw new TeamApiError("config", "문서 경로의 식별자 위치를 확인해 주세요.");
        path = path.replaceAll("{source_ref_id}", encodeURIComponent(sourceRefId));
      }
      url = new URL(path, base);
    } catch (error) {
      if (error instanceof TeamApiError) throw error;
      throw new TeamApiError("config", "API 주소 형식이 올바르지 않아요.");
    }
    if (!["https:", "http:"].includes(base.protocol) || !["https:", "http:"].includes(url.protocol)
      || base.username || base.password || url.username || url.password || base.origin !== url.origin) {
      throw new TeamApiError("config", "API는 인증정보 없는 HTTP 또는 HTTPS 주소를 사용해야 해요.");
    }
    return url;
  }

  async function request(url, { method = "GET", payload, signal } = {}) {
    signal?.throwIfAborted();
    if (typeof fetchImpl !== "function") throw new TeamApiError("config", "이 환경에서 네트워크 요청을 사용할 수 없어요.");
    const controller = new AbortController();
    const relay = () => controller.abort(signal.reason);
    signal?.addEventListener("abort", relay, { once: true });
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, config.timeoutMs ?? 30000);
    try {
      let response;
      try {
        response = await fetchImpl(url, {
          method, credentials: "omit", signal: controller.signal,
          headers: payload === undefined ? { Accept: "application/json" } : { Accept: "application/json", "Content-Type": "application/json" },
          ...(payload === undefined ? {} : { body: JSON.stringify(payload) }),
        });
      } catch (error) {
        if (signal?.aborted) throw signal.reason ?? error;
        if (timedOut) throw new TeamApiError("timeout", "서버 응답이 늦어 요청을 멈췄어요. 다시 시도해 주세요.");
        throw new TeamApiError("network", "서버에 연결하지 못했어요. 서버 주소와 네트워크·CORS 설정을 확인해 주세요.");
      }
      let body;
      try { body = await response.json(); } catch {
        if (signal?.aborted) throw signal.reason;
        if (timedOut) throw new TeamApiError("timeout", "서버 응답이 늦어 요청을 멈췄어요. 다시 시도해 주세요.");
        if (!response.ok) throw new TeamApiError("http", `서버 요청이 실패했어요 (HTTP ${response.status}).`, { httpStatus: response.status });
        failFormat("서버 응답을 JSON으로 읽지 못했어요.");
      }
      signal?.throwIfAborted();
      if (timedOut) throw new TeamApiError("timeout", "서버 응답이 늦어 요청을 멈췄어요. 다시 시도해 주세요.");
      if (!response.ok) {
        const code = typeof body?.error_code === "string" ? body.error_code : typeof body?.error?.code === "string" ? body.error.code : typeof body?.code === "string" ? body.code : null;
        throw new TeamApiError("http", `서버 요청이 실패했어요 (HTTP ${response.status}${code ? ` · ${code}` : ""}).`, { httpStatus: response.status, code });
      }
      return body;
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener("abort", relay);
    }
  }

  return {
    ready: missing.length === 0,
    missing,
    maxMessages,
    maxContentLength,
    async getSuggestions(level = "beginner", { signal } = {}) {
      if (!["beginner", "novice", "expert"].includes(level)) throw new TeamApiError("validation", "질문 등급이 올바르지 않아요.");
      const url = endpoint("suggestions");
      url.searchParams.set("level", level);
      const data = dataEnvelope(await request(url, { signal }));
      if (data.level !== level || !Array.isArray(data.suggestions) || data.suggestions.some(row => !nonempty(row?.id) || !nonempty(row?.text))) {
        failFormat("추천 질문의 등급 또는 목록 형식이 올바르지 않아요.");
      }
      return { level: data.level, suggestions: data.suggestions.map(row => ({ id: row.id, text: row.text })) };
    },
    async ask(messages, { signal } = {}) {
      const payload = { messages: validateTeamMessages(messages, { maxMessages, maxContentLength }) };
      return validateTeamAnswer(await request(endpoint("ask"), { method: "POST", payload, signal }));
    },
    async getDocument(sourceRefId, { signal } = {}) {
      signal?.throwIfAborted();
      const url = endpoint("document", sourceRefId);
      if (documentCache.has(sourceRefId)) return { ...documentCache.get(sourceRefId) };
      const data = dataEnvelope(await request(url, { signal }));
      if (data.source_ref_id !== sourceRefId || typeof data.markdown !== "string") {
        failFormat("요청한 원문 문서와 서버 응답이 일치하지 않아요.");
      }
      const result = { source_ref_id: data.source_ref_id, markdown: data.markdown };
      documentCache.set(sourceRefId, result);
      return { ...result };
    },
  };
}
