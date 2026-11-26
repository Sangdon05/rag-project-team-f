/** Presentation lifecycle checks with a minimal safe DOM; no browser package needed. */
import test from "node:test";
import assert from "node:assert/strict";
import { typeDialogue, speakDialogue } from "../frontend/dialogue.mjs";

function createHost() {
  class Node {
    constructor(tag, document) {
      this.tagName = tag; this.ownerDocument = document; this.children = []; this.attributes = new Map();
      this.value = ""; this.isConnected = true; this.hiddenAncestor = false;
      const classes = new Set();
      this.classList = { add: name => classes.add(name), remove: name => classes.delete(name), contains: name => classes.has(name) };
    }
    get textContent() { return this.tagName === "#text" ? this.value : this.children.map(child => child.textContent).join(""); }
    set textContent(value) { if (this.tagName === "#text") this.value = String(value); else this.replaceChildren(this.ownerDocument.createTextNode(String(value))); }
    set innerHTML(_) { throw new Error("HTML injection API must not be used"); }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = [...children]; }
    setAttribute(name, value) { this.attributes.set(name, value); }
    getAttribute(name) { return this.attributes.get(name) ?? null; }
    closest() { return this.hiddenAncestor ? {} : null; }
  }
  const listeners = new Map();
  const document = {
    hidden: false,
    createTextNode(text) { const node = new Node("#text", this); node.value = text; return node; },
    createElement(tag) { return new Node(tag, this); },
    addEventListener(event, callback) { if (!listeners.has(event)) listeners.set(event, new Set()); listeners.get(event).add(callback); },
    removeEventListener(event, callback) { listeners.get(event)?.delete(callback); },
    dispatch(event) { for (const callback of [...(listeners.get(event) ?? [])]) callback(); },
  };
  return new Node("div", document);
}

function withClock(run) {
  const originalSet = globalThis.setTimeout, originalClear = globalThis.clearTimeout;
  const timers = new Map(); let sequence = 0;
  globalThis.setTimeout = callback => { const id = ++sequence; timers.set(id, callback); return id; };
  globalThis.clearTimeout = id => timers.delete(id);
  const clock = {
    tick() { const next = timers.entries().next().value; if (next) { timers.delete(next[0]); next[1](); } },
    flush() { let count = 0; while (timers.size) { assert.ok(++count < 10000, "timer loop must terminate"); this.tick(); } },
    get pending() { return timers.size; },
  };
  try { run(clock); } finally { globalThis.setTimeout = originalSet; globalThis.clearTimeout = originalClear; }
}

test("instant dialogue preserves hostile text literally and chooses longest overlapping keywords", () => {
  const host = createHost(), text = "피카츄는 1.5배. <img src=x onerror=bad()> 피카츄";
  let completed = 0;
  const animation = typeDialogue(host, text, { instant: true, keywords: ["피카", "피카츄", "1", "1.5", "<img src=x onerror=bad()>"], onComplete: () => completed++ });
  assert.equal(host.textContent, text);
  assert.deepEqual(host.children.filter(node => node.tagName === "strong").map(node => node.textContent),
    ["피카츄", "1.5", "<img src=x onerror=bad()>", "피카츄"]);
  assert.ok(host.children.every(node => ["#text", "strong"].includes(node.tagName)));
  assert.equal(host.getAttribute("aria-live"), null);
  assert.equal(host.getAttribute("aria-busy"), "false");
  assert.equal(host.classList.contains("is-typing"), false);
  animation.finish(); animation.cancel(); assert.equal(completed, 1);
});

test("Korean, combining marks and a joined emoji type as complete graphemes", () => withClock(clock => {
  const host = createHost();
  typeDialogue(host, "가👩‍👩‍👧‍👦e\u0301끝", { keywords: ["👩", "👩‍👩‍👧‍👦"] });
  assert.equal(host.textContent, "");
  assert.equal(host.getAttribute("aria-busy"), "true");
  clock.tick(); assert.equal(host.textContent, "가");
  clock.tick(); assert.equal(host.textContent, "가👩‍👩‍👧‍👦");
  clock.tick(); assert.equal(host.textContent, "가👩‍👩‍👧‍👦e\u0301");
  clock.flush(); assert.equal(host.textContent, "가👩‍👩‍👧‍👦e\u0301끝");
  assert.equal(clock.pending, 0);
}));

test("finish reveals the exact remaining text once and cancels all pending ticks", () => withClock(clock => {
  const host = createHost(); let completed = 0;
  const animation = typeDialogue(host, "물대포 4배", { keywords: ["물대포", "4"], onComplete: () => completed++ });
  clock.tick(); animation.finish(); animation.finish(); clock.flush();
  assert.equal(host.textContent, "물대포 4배");
  assert.equal(completed, 1); assert.equal(clock.pending, 0);
}));

test("replacement and cancellation prevent old timers or finish handles from appending stale answers", () => withClock(clock => {
  const host = createHost(); let oldComplete = 0, newComplete = 0;
  const old = typeDialogue(host, "이전 질문의 긴 답변", { onComplete: () => oldComplete++ });
  clock.tick();
  typeDialogue(host, "새 답변", { onComplete: () => newComplete++ });
  old.finish(); clock.flush();
  assert.equal(host.textContent, "새 답변"); assert.equal(oldComplete, 0); assert.equal(newComplete, 1);
  const cancelled = typeDialogue(host, "중단할 답변");
  clock.tick(); cancelled.cancel(); const prefix = host.textContent; cancelled.finish(); clock.flush();
  assert.equal(host.textContent, prefix); assert.equal(host.getAttribute("aria-busy"), "false");
}));

test("hidden views, detached hosts and background documents cancel rather than finishing", () => withClock(clock => {
  for (const hide of [host => { host.hiddenAncestor = true; }, host => { host.isConnected = false; }, host => {
    host.ownerDocument.hidden = true; host.ownerDocument.dispatch("visibilitychange");
  }]) {
    const host = createHost(); let completed = 0;
    typeDialogue(host, "보이지 않을 때 멈출 답변", { onComplete: () => completed++ });
    clock.tick(); const prefix = host.textContent; hide(host); clock.flush();
    assert.equal(host.textContent, prefix); assert.equal(completed, 0);
    assert.equal(host.classList.contains("is-typing"), false);
  }
}));

function withSpeech(voices, run) {
  const originalSpeech = Object.getOwnPropertyDescriptor(globalThis, "speechSynthesis");
  const originalUtterance = Object.getOwnPropertyDescriptor(globalThis, "SpeechSynthesisUtterance");
  const spoken = []; let cancels = 0;
  const synthesis = { getVoices: () => voices, speak: utterance => spoken.push(utterance), cancel: () => { cancels++; } };
  Object.defineProperty(globalThis, "speechSynthesis", { configurable: true, value: synthesis });
  Object.defineProperty(globalThis, "SpeechSynthesisUtterance", { configurable: true, value: class { constructor(text) { this.text = text; } } });
  try { run({ synthesis, spoken, get cancels() { return cancels; } }); }
  finally {
    if (originalSpeech) Object.defineProperty(globalThis, "speechSynthesis", originalSpeech); else delete globalThis.speechSynthesis;
    if (originalUtterance) Object.defineProperty(globalThis, "SpeechSynthesisUtterance", originalUtterance); else delete globalThis.SpeechSynthesisUtterance;
  }
}

test("speech stays unsupported without a Korean voice and never substitutes another language", () => withSpeech([{ lang: "en-US" }], ({ spoken }) => {
  assert.equal(speakDialogue("안녕").supported, false); assert.equal(spoken.length, 0);
}));

test("explicit speech uses the Korean browser voice and delivers completion only once", () => withSpeech([{ lang: "ko-KR", name: "한국어" }], ({ spoken }) => {
  let ends = 0, errors = 0;
  const speech = speakDialogue("피카츄랑 준비할까?", { onEnd: () => ends++, onError: () => errors++ });
  assert.equal(speech.supported, true); assert.equal(spoken.length, 1);
  assert.equal(spoken[0].lang, "ko-KR"); assert.equal(spoken[0].voice.name, "한국어");
  assert.equal(spoken[0].text, "피카츄랑 준비할까?");
  spoken[0].onend({}); spoken[0].onend({}); spoken[0].onerror({});
  assert.equal(ends, 1); assert.equal(errors, 0);
}));

test("speech replacement cancels prior callbacks and reports a browser failure once", () => withSpeech([{ lang: "ko-KR" }], api => {
  let ends = 0, errors = 0;
  speakDialogue("이전 답변", { onEnd: () => ends++ });
  const second = speakDialogue("새 답변");
  assert.equal(api.spoken[0].onend, null); assert.equal(api.cancels, 1);
  second.cancel(); second.cancel(); assert.equal(api.cancels, 2); assert.equal(ends, 0);
  api.synthesis.speak = () => { throw new Error("browser failure"); };
  const failed = speakDialogue("실패할 답변", { onError: () => errors++ });
  assert.equal(failed.supported, false); assert.equal(errors, 1);
}));
