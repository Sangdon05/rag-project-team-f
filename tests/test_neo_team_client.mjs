import test from "node:test";
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { once } from "node:events";
import { TEAM_API } from "../frontend/neo-config.mjs";
import { createTeamApiClient, TeamApiError, validateTeamAnswer, validateTeamMessages } from "../frontend/neo-team-client.mjs";

const config = { baseUrl: "https://example.test", suggestionsPath: "/questions", askPath: "/chat", documentPath: "/documents/{source_ref_id}", timeoutMs: 200 };
const envelope = data => ({ success: true, data });
const answer = { answer: "롱스톤은 바위·땅 타입이에요[1].", mode: "rag", sources: [{ ref: 1, chunk_id: "pokemon-095-types", source_ref_id: "pokemon-095" }] };
const json = (body, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => body });
const isError = kind => error => error instanceof TeamApiError && error.kind === kind;

test('embedding metadata passes through only for RAG and never enters a later chat payload', async () => {
  const embedding = { query_model: 'solar-embedding-2-query', document_model: 'solar-embedding-2-passage' };
  let posted;
  const client = createTeamApiClient({ config, fetchImpl: async (_url, options) => {
    posted = JSON.parse(options.body);
    return json(envelope({ ...answer, embedding }));
  } });
  const result = await client.ask([{ role: 'user', content: '질문', embedding: { untrusted: true } }]);
  assert.deepEqual(result.embedding, embedding);
  assert.deepEqual(posted, { messages: [{ role: 'user', content: '질문' }] });
  for (const mode of ['mock', 'llm']) assert.throws(() => validateTeamAnswer(envelope({ ...answer, mode, embedding })), isError('format'));
  for (const invalid of [{ query_model: 'x' }, { query_model: 'x', document_model: '' },
    { query_model: 'x\u0000', document_model: 'y' }, { ...embedding, invented: true }]) {
    assert.throws(() => validateTeamAnswer(envelope({ ...answer, embedding: invalid })), isError('format'));
  }
  assert.equal(Object.hasOwn(validateTeamAnswer(envelope(answer)), 'embedding'), false);
});

test("published defaults use the team suggestion route and server-side content limits", () => {
  assert.equal(TEAM_API.suggestionsPath, "/api/v1/suggestion");
  assert.equal(TEAM_API.maxContentLength, null);
  assert.equal(TEAM_API.maxMessages, 20);
});

test("three-digit document identifiers preserve leading zeros", async () => {
  let requested;
  const source = { ref: 1, chunk_id: "pokemon:1#types", source_ref_id: "001" };
  const result = validateTeamAnswer(envelope({ answer: "답변[1]", mode: "rag", sources: [source] }));
  assert.equal(result.sources[0].source_ref_id, "001");
  const client = createTeamApiClient({ config, fetchImpl: async url => {
    requested = String(url);
    return json(envelope({ source_ref_id: "001", markdown: "# 원문 문서" }));
  } });
  assert.equal((await client.getDocument(result.sources[0].source_ref_id)).source_ref_id, "001");
  assert.equal(requested, "https://example.test/documents/001");
});

test("unverified deployment configuration never makes a request or supplies a mock answer", async () => {
  let calls = 0;
  const client = createTeamApiClient({ config: { ...TEAM_API, baseUrl: '', suggestionsPath: '', askPath: '', documentPath: '' }, fetchImpl: async () => { calls++; return json(envelope(answer)); } });
  assert.equal(client.ready, false);
  assert.equal(client.missing.length, 4);
  await assert.rejects(client.ask([{ role: "user", content: "피카츄는 무슨 타입이야?" }]), isError("config"));
  await assert.rejects(client.getSuggestions(), isError("config"));
  await assert.rejects(client.getDocument("pokemon"), isError("config"));
  assert.equal(calls, 0);
});

test("all persona levels and an empty suggestion list preserve the actual response", async () => {
  const urls = [];
  const client = createTeamApiClient({ config, fetchImpl: async (url, init) => {
    urls.push(String(url));
    assert.equal(init.method, "GET");
    assert.ok(!("body" in init));
    const level = url.searchParams.get("level");
    return json(envelope({ level, suggestions: level === "expert" ? [] : [{ id: `${level}-01`, text: "피카츄는 무슨 타입이야?" }] }));
  } });
  for (const level of ["beginner", "novice", "expert"]) {
    const result = await client.getSuggestions(level);
    assert.equal(result.level, level);
    assert.equal(result.suggestions.length, level === "expert" ? 0 : 1);
  }
  assert.equal((await client.getSuggestions()).level, "beginner");
  assert.equal(urls.length, 4);
  await assert.rejects(client.getSuggestions(""), isError("validation"));
  await assert.rejects(client.getSuggestions("advanced"), isError("validation"));
});

test("suggestions reject stale levels and malformed responses", async () => {
  for (const data of [{ level: "novice", suggestions: [] }, { level: "beginner", suggestions: [{ id: "x", text: "" }] }, { level: "beginner" }]) {
    const client = createTeamApiClient({ config, fetchImpl: async () => json(envelope(data)) });
    await assert.rejects(client.getSuggestions("beginner"), isError("format"));
  }
});

test("POST sends only messages, strips citations in assistant content, and preserves the answer", async () => {
  const original = [{ role: "user", content: " 피카츄는? ", persona: "P1" }, { role: "assistant", content: "전기 타입이에요[1][2]." }, { role: "user", content: "그럼 롱스톤은?", mate_id: "jiu" }];
  let sent;
  const client = createTeamApiClient({ config, fetchImpl: async (url, init) => {
    sent = { url: String(url), ...init, parsed: JSON.parse(init.body) };
    return json(envelope(answer));
  } });
  const result = await client.ask(original);
  assert.equal(sent.url, "https://example.test/chat");
  assert.equal(sent.method, "POST");
  assert.equal(sent.credentials, "omit");
  assert.equal(sent.headers["Content-Type"], "application/json");
  assert.deepEqual(sent.parsed, { messages: [{ role: "user", content: "피카츄는?" }, { role: "assistant", content: "전기 타입이에요." }, { role: "user", content: "그럼 롱스톤은?" }] });
  assert.equal(original[1].content, "전기 타입이에요[1][2].");
  assert.deepEqual(result, answer);
});

test("message validation rejects invalid role order, blank content and invalid limits before sending", () => {
  const invalid = [[], [{ role: "assistant", content: "a" }], [{ role: "user", content: " " }], [{ role: "system", content: "x" }],
    [{ role: "user", content: "q" }, { role: "assistant", content: "a" }],
    [{ role: "user", content: "q" }, { role: "user", content: "q" }, { role: "user", content: "q" }],
    [{ role: "user", content: "q" }, { role: "assistant", content: "[1]" }, { role: "user", content: "q" }]];
  for (const messages of invalid) assert.throws(() => validateTeamMessages(messages), isError("validation"));
  assert.throws(() => validateTeamMessages([{ role: "user", content: "abc" }], { maxContentLength: 2 }), isError("validation"));
  assert.throws(() => validateTeamMessages([{ role: "user", content: "x" }], { maxMessages: 0 }), isError("config"));
  assert.deepEqual(validateTeamMessages([{ role: "user", content: "😀a" }], { maxContentLength: 2 }), [{ role: "user", content: "😀a" }]);
  const history = Array.from({ length: 19 }, (_, i) => ({ role: i % 2 ? "assistant" : "user", content: String(i) }));
  assert.equal(validateTeamMessages(history).length, 19);
  assert.throws(() => validateTeamMessages([...history, { role: "assistant", content: "a" }, { role: "user", content: "q" }]), isError("validation"));
});

test("actual mock, llm and rag modes remain distinct, including no-source success", async () => {
  for (const mode of ["mock", "llm", "rag"]) {
    const client = createTeamApiClient({ config, fetchImpl: async () => json(envelope({ answer: "근거를 확인할 수 없어요.", mode, sources: [] })) });
    assert.deepEqual(await client.ask([{ role: "user", content: "질문" }]), { answer: "근거를 확인할 수 없어요.", mode, sources: [] });
  }
});

test("citation references are kept without inventing metadata; identical refs deduplicate and conflicts reject", () => {
  const source = answer.sources[0];
  assert.deepEqual(validateTeamAnswer(envelope({ ...answer, sources: [source, source] })), answer);
  assert.throws(() => validateTeamAnswer(envelope({ ...answer, sources: [source, { ...source, chunk_id: "different" }] })), isError("format"));
  for (const data of [{ ...answer, mode: "stream" }, { ...answer, answer: "" }, { ...answer, sources: [{ ...source, ref: "1" }] }, { ...answer, sources: [{ ref: 1 }] }]) {
    assert.throws(() => validateTeamAnswer(envelope(data)), isError("format"));
  }
  assert.deepEqual(validateTeamAnswer(envelope({ ...answer, answer: "미등록 번호[9]", sources: [] })).sources, []);
});

test("source document ID is encoded as one segment; lazy cache returns original Markdown", async () => {
  let calls = 0, requested;
  const id = "문서/95?mode=1#types";
  const markdown = "# 롱스톤\n\n<script>alert(1)</script>\n\n[링크](javascript:alert(1))";
  const client = createTeamApiClient({ config, fetchImpl: async (url, init) => {
    calls++; requested = String(url);
    assert.equal(init.method, "GET");
    return json(envelope({ source_ref_id: id, markdown }));
  } });
  assert.equal(calls, 0);
  assert.deepEqual(await client.getDocument(id), { source_ref_id: id, markdown });
  assert.equal(requested, `https://example.test/documents/${encodeURIComponent(id)}`);
  const result = await client.getDocument(id);
  result.markdown = "mutated";
  assert.equal((await client.getDocument(id)).markdown, markdown);
  assert.equal(calls, 1);
  await assert.rejects(client.getDocument(".."), isError("validation"));
});

test("document mismatches and failures do not poison the cache", async () => {
  let calls = 0;
  const client = createTeamApiClient({ config, fetchImpl: async () => {
    calls++;
    if (calls === 1) return json(envelope({ source_ref_id: "wrong", markdown: "# wrong" }));
    return json(envelope({ source_ref_id: "pokemon", markdown: "# correct" }));
  } });
  await assert.rejects(client.getDocument("pokemon"), isError("format"));
  assert.equal((await client.getDocument("pokemon")).markdown, "# correct");
  assert.equal(calls, 2);
});

test("HTTP error status and code survive without exposing upstream messages", async () => {
  for (const [status, code] of [[400, "VALIDATION_ERROR"], [404, "DOCUMENT_NOT_FOUND"], [405, "METHOD_NOT_ALLOWED"], [500, "INTERNAL_ERROR"], [502, "ANSWER_GENERATION_FAILED"]]) {
    const client = createTeamApiClient({ config, fetchImpl: async () => json({ success: false, error_code: code, message: "private upstream detail" }, status) });
    await assert.rejects(client.ask([{ role: "user", content: "질문" }]), error => {
      assert.equal(error.httpStatus, status);
      assert.equal(error.code, code);
      assert.ok(!error.message.includes("private"));
      return isError("http")(error);
    });
  }
});

test("malformed success envelopes and non-JSON success fail clearly", async () => {
  for (const response of [json(answer), json({ success: false, data: answer }), { ok: true, status: 200, json: async () => { throw new SyntaxError("bad JSON"); } }]) {
    const client = createTeamApiClient({ config, fetchImpl: async () => response });
    await assert.rejects(client.ask([{ role: "user", content: "q" }]), isError("format"));
  }
});

test("network and timeout failures never return a local replacement", async () => {
  const network = createTeamApiClient({ config, fetchImpl: async () => { throw new TypeError("Failed to fetch"); } });
  await assert.rejects(network.getSuggestions(), isError("network"));
  const timeout = createTeamApiClient({ config: { ...config, timeoutMs: 10 }, fetchImpl: (_url, init) => new Promise((_, reject) => init.signal.addEventListener("abort", () => reject(init.signal.reason))) });
  await assert.rejects(timeout.ask([{ role: "user", content: "q" }]), isError("timeout"));
});

test("caller abort is preserved and prevents late user responses or cached document delivery", async () => {
  const controller = new AbortController();
  const client = createTeamApiClient({ config, fetchImpl: (_url, init) => new Promise((_, reject) => init.signal.addEventListener("abort", () => reject(init.signal.reason))) });
  const pending = client.ask([{ role: "user", content: "q" }], { signal: controller.signal });
  controller.abort();
  await assert.rejects(pending, error => error.name === "AbortError");
  await assert.rejects(client.getSuggestions("novice", { signal: controller.signal }), error => error.name === "AbortError");
  await assert.rejects(client.getDocument("pokemon", { signal: controller.signal }), error => error.name === "AbortError");
});

test("API URLs reject script schemes, userinfo and cross-origin endpoint overrides", async () => {
  for (const patch of [{ baseUrl: "javascript:alert(1)" }, { baseUrl: "https://user:secret@example.test" }, { askPath: "https://another.test/chat" }, { askPath: "javascript:alert(1)" }]) {
    const client = createTeamApiClient({ config: { ...config, ...patch }, fetchImpl: () => { throw new Error("must not fetch"); } });
    await assert.rejects(client.ask([{ role: "user", content: "q" }]), isError("config"));
  }
});

test("real HTTP transport verifies all three user-provided schemas against an explicitly labeled fixture", async () => {
  const requests = [];
  const server = createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = Buffer.concat(chunks).toString("utf8");
    requests.push({ method: req.method, url: req.url, body });
    res.writeHead(200, { "Content-Type": "application/json" });
    const data = req.url.startsWith("/questions") ? { level: "novice", suggestions: [{ id: "fixture-01", text: "타입이 뭐야?" }] }
      : req.url === "/chat" ? answer : { source_ref_id: "pokemon-095", markdown: "# 롱스톤\n\n바위 / 땅" };
    res.end(JSON.stringify(envelope(data)));
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  try {
    const client = createTeamApiClient({ config: { ...config, baseUrl: `http://127.0.0.1:${server.address().port}`, timeoutMs: 1000 } });
    assert.equal((await client.getSuggestions("novice")).suggestions[0].id, "fixture-01");
    assert.deepEqual(await client.ask([{ role: "user", content: "롱스톤은?" }]), answer);
    assert.match((await client.getDocument("pokemon-095")).markdown, /바위 \/ 땅/);
    assert.deepEqual(requests.map(row => [row.method, row.url]), [["GET", "/questions?level=novice"], ["POST", "/chat"], ["GET", "/documents/pokemon-095"]]);
    assert.deepEqual(JSON.parse(requests[1].body), { messages: [{ role: "user", content: "롱스톤은?" }] });
  } finally {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
  }
});
