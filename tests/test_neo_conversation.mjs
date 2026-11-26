import test from "node:test";
import assert from "node:assert/strict";
import {
  buildApiMessages, createConversationStore, sortConversation, stripAnswerCitations, validateApiMessages,
} from "../frontend/neo-conversation.mjs";

const record = (index, role, extra = {}) => ({
  conversation_id: "conversation:P1", persona_id: "P1", mate_id: "jiwoo",
  message_id: `${role}-${index}`, role, content: `${role} ${index}`,
  created_at: new Date(Date.UTC(2026, 10, 26, 0, 0, index * 2 + (role === "assistant" ? 1 : 0))).toISOString(),
  mode: role === "assistant" ? "rag" : null, sources: [], request_status: "completed", ...extra,
});
const pair = (index, extra = {}) => [record(index, "user", extra), record(index, "assistant", { reply_to: `user-${index}`, ...extra })];
const current = (extra = {}) => record(100, "user", { request_status: "pending", content: "새 질문", ...extra });

test("first request contains only the new user question and no local metadata", () => {
  assert.deepEqual(buildApiMessages([], current()), [{ role: "user", content: "새 질문" }]);
});

test("follow-up includes a completed pair; removes citations only from assistant payload", () => {
  const history = pair(1);
  history[0].content = " [1]이 무슨 뜻이야? ";
  history[1].content = " 피카츄는 전기 타입이야[1][2]. 원문은 [안내](https://example.com). ";
  history[1].sources = [{ ref: 1, chunk_id: "pokemon-025", source_ref_id: "pokemon" }];
  const before = structuredClone(history);
  assert.deepEqual(buildApiMessages(history, current()), [
    { role: "user", content: "[1]이 무슨 뜻이야?" },
    { role: "assistant", content: "피카츄는 전기 타입이야. 원문은 [안내](https://example.com)." },
    { role: "user", content: "새 질문" },
  ]);
  assert.deepEqual(history, before);
});

test("default context retains nine recent complete pairs plus new question, preserving full log", () => {
  const history = Array.from({ length: 30 }, (_, index) => pair(index)).flat();
  const payload = buildApiMessages(history, current());
  assert.equal(payload.length, 19);
  assert.equal(payload[0].content, "user 21");
  assert.equal(payload.at(-1).content, "새 질문");
  assert.equal(history.length, 60);
  for (let index = 0; index < payload.length; index += 1) assert.equal(payload[index].role, index % 2 ? "assistant" : "user");
});

test("custom even/odd maximum always produces a valid odd message count", () => {
  const history = Array.from({ length: 8 }, (_, index) => pair(index)).flat();
  for (const [maxMessages, expected] of [[1, 1], [2, 1], [3, 3], [4, 3], [5, 5], [20, 17]]) {
    assert.equal(buildApiMessages(history, current(), { maxMessages }).length, expected);
  }
});

test("personas and conversation IDs never mix even if history is combined accidentally", () => {
  const history = [
    ...pair(1),
    ...pair(2, { persona_id: "P2", conversation_id: "conversation:P2", mate_id: "iseul" }),
    ...pair(3, { conversation_id: "another:P1" }),
    ...pair(4, { persona_id: "P3", conversation_id: "conversation:P3", mate_id: "woong" }),
  ];
  assert.deepEqual(buildApiMessages(history, current()).map(row => row.content), ["user 1", "assistant 1", "새 질문"]);
});

test("failed, interrupted and unfinished exchanges never enter API history", () => {
  const history = [
    ...pair(1),
    record(2, "user", { request_status: "failed" }),
    record(2, "assistant", { request_status: "completed", reply_to: "user-2" }),
    record(3, "user"), record(3, "assistant", { request_status: "pending", reply_to: "user-3" }),
    record(4, "user", { request_status: "pending" }),
    ...pair(5),
  ];
  assert.deepEqual(buildApiMessages(history, current()).map(row => row.content), ["user 1", "assistant 1", "user 5", "assistant 5", "새 질문"]);
});

test("retry excludes the current question's existing record and sends it exactly once", () => {
  const question = current({ request_status: "failed" });
  const history = [...pair(1), question];
  const payload = buildApiMessages(history, question);
  assert.equal(payload.filter(row => row.content === "새 질문").length, 1);
  assert.equal(history.length, 3);
});

test("greetings, unmatched answers and duplicate completed answers are excluded", () => {
  const history = [
    record(0, "assistant", { decoration: true, content: "안녕!" }),
    ...pair(1),
    record(2, "assistant", { reply_to: "user-1", content: "중복 답변" }),
    record(3, "assistant", { reply_to: "missing-user" }),
    ...pair(4, { decoration: true }),
  ];
  assert.deepEqual(buildApiMessages(history, current()).map(row => row.content), ["user 1", "assistant 1", "새 질문"]);
});

test("legacy adjacent successful pairs remain usable without reply_to metadata", () => {
  const history = [record(1, "user"), record(1, "assistant")];
  assert.equal(buildApiMessages(history, current()).length, 3);
});

test("invalid/over-limit historical content excludes its whole pair; new over-limit question fails", () => {
  const history = [
    ...pair(1),
    record(2, "user", { content: "오래된 질문이 너무 길어졌어요" }), record(2, "assistant", { content: "짧아", reply_to: "user-2" }),
    record(3, "user", { content: "질문" }), record(3, "assistant", { content: "[1]", reply_to: "user-3" }),
  ];
  assert.deepEqual(buildApiMessages(history, current(), { maxContentLength: 12 }).map(row => row.content), ["user 1", "assistant 1", "새 질문"]);
  assert.throws(() => buildApiMessages([], current({ content: "너무 길어요" }), { maxContentLength: 2 }), /limit/);
});

test("Unicode content limit counts code points without truncating the answer", () => {
  assert.deepEqual(buildApiMessages([], current({ content: "😀😀" }), { maxContentLength: 2 }), [{ role: "user", content: "😀😀" }]);
  assert.throws(() => buildApiMessages([], current({ content: "😀😀😀" }), { maxContentLength: 2 }), /limit/);
});

test("payload validation rejects non-alternating roles, empty text and invalid bounds", () => {
  assert.throws(() => validateApiMessages([]), /odd/);
  assert.throws(() => validateApiMessages([{ role: "system", content: "hello" }]), /alternate/);
  assert.throws(() => validateApiMessages([{ role: "user", content: "  " }]), /empty/);
  assert.throws(() => validateApiMessages([{ role: "user", content: "q" }, { role: "user", content: "a" }, { role: "user", content: "q" }]), /alternate/);
  assert.throws(() => buildApiMessages([], current(), { maxMessages: 0 }), /limit/);
  assert.throws(() => buildApiMessages([], current(), { maxMessages: 2.5 }), /limit/);
  assert.throws(() => buildApiMessages([], current(), { maxContentLength: 0 }), /limit|empty/);
  assert.throws(() => buildApiMessages([], current({ persona_id: "P4" })), /persona/);
});

test("chronological sorting preserves the caller's array and orders same-time linked pairs", () => {
  const question = record(1, "user"), answer = record(1, "assistant", { reply_to: "user-1", created_at: question.created_at });
  const input = [record(5, "user"), answer, question];
  const ordered = sortConversation(input);
  assert.deepEqual(ordered.map(row => row.message_id), ["user-1", "assistant-1", "user-5"]);
  assert.equal(input[0].message_id, "user-5");
  assert.equal(stripAnswerCitations("설명[1][21] [문서] [x]"), "설명 [문서] [x]");
});

test("storage fails explicitly when IndexedDB is unavailable; invalid records never reach storage", async () => {
  const store = createConversationStore({ indexedDB: null });
  await assert.rejects(store.load("P1"), /IndexedDB/);
  await assert.rejects(store.clearPersona("P1"), /IndexedDB/);
  await assert.rejects(store.clearPersona("P4"), /persona/);
  await assert.rejects(store.save(record(1, "user", { request_status: "unknown" })), /status/);
  await assert.rejects(store.save(record(1, "user", { persona_id: "P4" })), /persona/);
  await assert.rejects(store.save(record(1, "user", { created_at: "yesterday" })), /created_at/);
  await store.close();
  await assert.rejects(store.load("P1"), /closed/);
});
