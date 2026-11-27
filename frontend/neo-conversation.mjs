/** Browser-local conversation records. UI messages and API history are separate views. */
import { normalizeEmbedding } from './neo-embedding.mjs';
const PERSONAS = new Set(["P1", "P2", "P3"]);
const ROLES = new Set(["user", "assistant"]);
const STATUSES = new Set(["pending", "completed", "failed"]);
const MODES = new Set(["mock", "llm", "rag"]);
const clone = value => structuredClone(value);

/** Message ID (UUID v4). crypto.randomUUID exists only in secure contexts (HTTPS, localhost),
 * so plain-HTTP deployments fall back to crypto.getRandomValues, which is available everywhere. */
export function createMessageId(cryptoImpl = globalThis.crypto) {
  if (typeof cryptoImpl?.randomUUID === "function") return cryptoImpl.randomUUID();
  if (typeof cryptoImpl?.getRandomValues !== "function") throw new Error("A random number source is required.");
  const bytes = cryptoImpl.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, b => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function requirePersona(personaId) {
  if (!PERSONAS.has(personaId)) throw new TypeError("Unknown conversation persona.");
  return personaId;
}
function requiredText(value, name) {
  if (typeof value !== "string" || !value.trim()) throw new TypeError(`${name} must be nonempty text.`);
  return value;
}
function normalizeRecord(record) {
  if (!record || typeof record !== "object") throw new TypeError("A conversation record is required.");
  requirePersona(record.persona_id);
  requiredText(record.conversation_id, "conversation_id");
  requiredText(record.message_id, "message_id");
  requiredText(record.mate_id, "mate_id");
  requiredText(record.content, "content");
  if (!ROLES.has(record.role)) throw new TypeError("Unsupported conversation role.");
  if (!STATUSES.has(record.request_status)) throw new TypeError("Unsupported request status.");
  if (typeof record.created_at !== "string" || !Number.isFinite(Date.parse(record.created_at))) {
    throw new TypeError("created_at must be a valid date string.");
  }
  if (record.mode != null && !MODES.has(record.mode)) throw new TypeError("Unsupported answer mode.");
  if (record.sources != null && !Array.isArray(record.sources)) throw new TypeError("sources must be an array.");
  const embedding = normalizeEmbedding(record.embedding);
  if (embedding && (record.role !== 'assistant' || record.mode !== 'rag')) throw new TypeError('Only a RAG answer can identify an embedding model.');
  const normalized = { ...record, mode: record.mode ?? null, sources: record.sources ?? [] };
  if (embedding) normalized.embedding = embedding;
  return clone(normalized);
}

/** Stable chronological order; linked questions precede answers with the same timestamp. */
export function sortConversation(messages) {
  return [...messages].sort((a, b) => {
    const time = Date.parse(a.created_at) - Date.parse(b.created_at);
    if (time) return time;
    if (b.reply_to === a.message_id) return -1;
    if (a.reply_to === b.message_id) return 1;
    return 0;
  });
}

/**
 * No memory-only fallback: persistence failures must be visible to the caller.
 * Pending records are recovered explicitly once on page initialization, never on every load.
 */
export function createConversationStore({ indexedDB = globalThis.indexedDB, dbName = "kanto-neo-conversations" } = {}) {
  let connection;
  let opening;
  let closed = false;
  const open = () => {
    if (closed) return Promise.reject(new Error("The conversation store is closed."));
    if (!indexedDB?.open) return Promise.reject(new Error("This browser cannot save conversations with IndexedDB."));
    if (connection) return Promise.resolve(connection);
    if (opening) return opening;
    opening = new Promise((resolve, reject) => {
      const request = indexedDB.open(dbName, 1);
      request.onupgradeneeded = () => {
        const db = request.result;
        const messages = db.createObjectStore("messages", { keyPath: ["persona_id", "message_id"] });
        messages.createIndex("persona_id", "persona_id", { unique: false });
      };
      request.onerror = () => reject(request.error ?? new Error("Could not open conversation storage."));
      request.onblocked = () => reject(new Error("Conversation storage is blocked by another open page."));
      request.onsuccess = () => {
        if (closed) { request.result.close(); reject(new Error("The conversation store is closed.")); return; }
        connection = request.result;
        connection.onversionchange = () => { connection.close(); connection = undefined; opening = undefined; };
        resolve(connection);
      };
    }).catch(error => { opening = undefined; throw error; });
    return opening;
  };

  async function transact(mode, action) {
    const db = await open();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction("messages", mode);
      let result;
      transaction.oncomplete = () => resolve(result);
      transaction.onabort = () => reject(transaction.error ?? new Error("Conversation save was interrupted."));
      transaction.onerror = () => reject(transaction.error ?? new Error("Conversation storage failed."));
      try { action(transaction.objectStore("messages"), value => { result = value; }); }
      catch (error) { transaction.abort(); reject(error); }
    });
  }

  async function saveMany(records) {
    const validated = records.map(normalizeRecord);
    return transact("readwrite", (store, done) => {
      for (const record of validated) store.put(record);
      done(clone(validated));
    });
  }

  return {
    async load(personaId) {
      requirePersona(personaId);
      const records = await transact("readonly", (store, done) => {
        const request = store.index("persona_id").getAll(personaId);
        request.onsuccess = () => done(request.result);
      });
      return sortConversation(records);
    },
    async save(record) { return (await saveMany([record]))[0]; },
    saveMany,
    async clearPersona(personaId) {
      requirePersona(personaId);
      // One transaction: a failed deletion rolls back every row for this persona.
      return transact("readwrite", (store, done) => {
        let count = 0;
        const request = store.index("persona_id").openCursor(personaId);
        request.onsuccess = () => {
          const cursor = request.result;
          if (!cursor) { done(count); return; }
          cursor.delete(); count += 1; cursor.continue();
        };
      });
    },
    async recoverPending(personaId) {
      requirePersona(personaId);
      return transact("readwrite", (store, done) => {
        let count = 0;
        const request = store.index("persona_id").openCursor(personaId);
        request.onsuccess = () => {
          const cursor = request.result;
          if (!cursor) { done(count); return; }
          if (cursor.value.request_status === "pending") {
            cursor.update({ ...cursor.value, request_status: "failed", error_code: "REQUEST_INTERRUPTED" });
            count += 1;
          }
          cursor.continue();
        };
      });
    },
    async close() {
      closed = true;
      if (connection) { connection.close(); connection = undefined; }
    },
  };
}

export function stripAnswerCitations(content) {
  return content.replace(/\[\d+\]/gu, "");
}

function apiContent(content, maxContentLength, { assistant = false } = {}) {
  if (typeof content !== "string") throw new TypeError("Message content must be text.");
  const cleaned = (assistant ? stripAnswerCitations(content) : content).trim();
  if (!cleaned) throw new TypeError("Message content cannot be empty.");
  if ([...cleaned].length > maxContentLength) throw new RangeError("Message content exceeds the API limit.");
  return cleaned;
}

/** Validate the exact role/content payload immediately before POST. */
export function validateApiMessages(messages, { maxMessages = 20, maxContentLength = Infinity } = {}) {
  if (!Number.isSafeInteger(maxMessages) || maxMessages < 1) throw new RangeError("Invalid API message limit.");
  if (!(maxContentLength > 0)) throw new RangeError("Invalid API content limit.");
  if (!Array.isArray(messages) || !messages.length || messages.length > maxMessages || messages.length % 2 !== 1) {
    throw new RangeError("API history must contain an odd number of messages within the API limit.");
  }
  return messages.map((message, index) => {
    const expected = index % 2 ? "assistant" : "user";
    if (message?.role !== expected) throw new TypeError("API history must alternate user and assistant, beginning and ending with user.");
    return { role: expected, content: apiContent(message.content, maxContentLength, { assistant: expected === "assistant" }) };
  });
}

/**
 * Send recent completed pairs plus the new/retried user question. Never shorten the local log.
 * Decoration/greeting rows, failed requests and incomplete pairs do not become server context.
 */
export function buildApiMessages(history, currentUserMessage, { maxMessages = 20, maxContentLength = Infinity } = {}) {
  if (!Number.isSafeInteger(maxMessages) || maxMessages < 1) throw new RangeError("Invalid API message limit.");
  if (currentUserMessage?.role !== "user") throw new TypeError("The current question must be a user message.");
  const personaId = requirePersona(currentUserMessage.persona_id);
  const conversationId = requiredText(currentUserMessage.conversation_id, "conversation_id");
  const currentId = requiredText(currentUserMessage.message_id, "message_id");
  const currentContent = apiContent(currentUserMessage.content, maxContentLength);
  const rows = sortConversation(history).filter(row => row.persona_id === personaId
    && row.conversation_id === conversationId && row.message_id !== currentId && !row.decoration);
  const pairs = [];
  const usedUsers = new Set();
  const usersById = new Map(rows.filter(row => row.role === "user").map(row => [row.message_id, row]));
  for (let index = 0; index < rows.length; index += 1) {
    const answer = rows[index];
    if (answer.role !== "assistant" || answer.request_status !== "completed") continue;
    const question = answer.reply_to ? usersById.get(answer.reply_to) : rows[index - 1];
    if (question?.role !== "user" || question.request_status !== "completed" || usedUsers.has(question.message_id)) continue;
    if (Date.parse(question.created_at) > Date.parse(answer.created_at)) continue;
    try {
      const pair = [
        { role: "user", content: apiContent(question.content, maxContentLength) },
        { role: "assistant", content: apiContent(answer.content, maxContentLength, { assistant: true }) },
      ];
      usedUsers.add(question.message_id);
      pairs.push(pair);
    } catch {
      // A formerly valid record can exceed a later server limit; exclude the whole pair.
    }
  }
  const maxPairs = Math.floor((maxMessages - 1) / 2);
  const recent = maxPairs ? pairs.slice(-maxPairs).flat() : [];
  return validateApiMessages([...recent, { role: "user", content: currentContent }], { maxMessages, maxContentLength });
}
