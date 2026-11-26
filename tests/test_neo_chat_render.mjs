import test from "node:test";
import assert from "node:assert/strict";
import { safeDocumentUrl, renderCitedAnswer, renderMarkdown, createOverlayScroll } from "../frontend/neo-chat-render.mjs";

function createDom() {
  class Node {
    constructor(tagName, ownerDocument, value = "") {
      this.tagName = tagName; this.ownerDocument = ownerDocument; this.value = value;
      this.children = []; this.attributes = new Map(); this.listeners = new Map();
      this.scrollTop = 0; this.scrollHeight = 0; this.clientHeight = 100;
    }
    get textContent() { return this.tagName === "#text" ? this.value : this.children.map(child => child.textContent).join(""); }
    set textContent(value) { this.replaceChildren(this.ownerDocument.createTextNode(String(value))); }
    set innerHTML(_) { throw new Error("Unsafe HTML insertion"); }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = children; }
    setAttribute(name, value) { this.attributes.set(name, value); }
    getAttribute(name) { return this.attributes.get(name) ?? null; }
    addEventListener(name, callback) { if (!this.listeners.has(name)) this.listeners.set(name, new Set()); this.listeners.get(name).add(callback); }
    removeEventListener(name, callback) { this.listeners.get(name)?.delete(callback); }
    dispatch(name, event = {}) { for (const callback of this.listeners.get(name) ?? []) callback(event); }
    closest() { return null; }
    scrollTo({ top }) { this.scrollTop = top; }
  }
  let sequence = 0;
  const frames = new Map();
  const observers = [];
  const document = {
    createElement(tag) { return new Node(tag, this); },
    createTextNode(value) { return new Node("#text", this, String(value)); },
    defaultView: {
      requestAnimationFrame(callback) { const id = ++sequence; frames.set(id, callback); return id; },
      cancelAnimationFrame(id) { frames.delete(id); },
      ResizeObserver: class {
        constructor(callback) { this.callback = callback; observers.push(this); }
        observe() {}
        disconnect() { this.disconnected = true; }
      },
    },
  };
  return {
    document, host: document.createElement("div"), observers,
    flush() { const callbacks = [...frames.values()]; frames.clear(); for (const callback of callbacks) callback(); },
    get pending() { return frames.size; },
  };
}
function all(node) { return [node, ...node.children.flatMap(all)]; }
function byTag(node, tag) { return all(node).filter(child => child.tagName === tag); }

test("document links allow explicit HTTP(S) and reject executable, ambiguous or credentialed URLs", () => {
  assert.equal(safeDocumentUrl("https://example.com/도감"), "https://example.com/%EB%8F%84%EA%B0%90");
  assert.equal(safeDocumentUrl(" HTTP://example.com/x "), "http://example.com/x");
  for (const value of ["javascript:alert(1)", "data:text/html,bad", "vbscript:bad", "//evil.example", "/relative", "#local", "https://user:password@example.com", "https://exa\nmple.com", "https:\\example.com", "https://", null]) {
    assert.equal(safeDocumentUrl(value), null, String(value));
  }
});

test("citations are scoped to each answer, repeated refs stay linked and unknown refs stay literal", () => {
  const { host, document } = createDom();
  const sources = [{ ref: 1, chunk_id: "one", source_ref_id: "pokemon" }, { ref: 1, chunk_id: "duplicate", source_ref_id: "wrong" }];
  const clicked = [];
  renderCitedAnswer(host, "타입[1], 반복[1], 미확인[9] <img onerror=bad()>", sources, source => clicked.push(source));
  assert.equal(host.textContent, "타입[1], 반복[1], 미확인[9] <img onerror=bad()>");
  const buttons = byTag(host, "button"); assert.equal(buttons.length, 2);
  buttons.forEach(button => button.dispatch("click"));
  assert.deepEqual(clicked, [sources[0], sources[0]]);
  assert.equal(byTag(host, "img").length, 0);
  const second = document.createElement("div");
  const other = { ref: 1, chunk_id: "other", source_ref_id: "chart" };
  renderCitedAnswer(second, "다른 답[1]", [other], source => clicked.push(source));
  byTag(second, "button")[0].dispatch("click"); assert.equal(clicked.at(-1), other);
  renderCitedAnswer(host, "출처 없음[1]", []); assert.equal(byTag(host, "button").length, 0);
});

test("Markdown raw HTML, scripts and images stay inert while source structure remains readable", () => {
  const { host } = createDom();
  renderMarkdown(host, "# 롱스톤\n\n<script>alert('x')</script>\n<img src=x onerror=bad()>\n\n![외부](https://evil.example/tracker.png)\n\n```html\n<img src=x onerror=bad()>\n```\n\n- **바위** / 땅\n- `Electric`\n\n| 타입 | 배율 |\n| --- | ---: |\n| 전기 | 0 |\n");
  assert.equal(byTag(host, "h1")[0].textContent, "롱스톤");
  assert.equal(byTag(host, "strong")[0].textContent, "바위");
  assert.equal(byTag(host, "pre")[0].textContent, "<img src=x onerror=bad()>");
  assert.equal(byTag(host, "table").length, 1);
  assert.equal(byTag(host, "th")[0].getAttribute("scope"), "col");
  assert.equal(byTag(host, "td").at(-1).textContent, "0");
  assert.equal(byTag(host, "script").length, 0); assert.equal(byTag(host, "img").length, 0);
  assert.ok(host.textContent.includes("<script>alert('x')</script>"));
  assert.ok(host.textContent.includes("[이미지: 외부]"));
  assert.ok(all(host).every(node => ![...node.attributes.keys()].some(name => name.startsWith("on"))));
});

test("Markdown links block dangerous schemes and retain nested URL parentheses safely", () => {
  const { host } = createDom();
  renderMarkdown(host, "[정상](https://example.com/a_(b)) [공격](javascript:alert(1)) [데이터](data:text/html,bad) [가짜](//example.com) [인용](https://example.com/\"onmouseover=bad)");
  const anchors = byTag(host, "a"); assert.equal(anchors.length, 2);
  assert.equal(anchors[0].getAttribute("href"), "https://example.com/a_(b)");
  assert.equal(anchors[0].getAttribute("target"), "_blank");
  assert.equal(anchors[0].getAttribute("rel"), "noopener noreferrer");
  assert.ok(anchors[1].getAttribute("href").includes("%22onmouseover=bad"));
  assert.equal(anchors[1].getAttribute("onmouseover"), null);
  assert.ok(host.textContent.includes("[공격](javascript:alert(1))"));
});

test("overlay follows its own end, respects a reader scrolling up, and resumes only explicitly or near the end", () => {
  const dom = createDom(), scroller = dom.host, content = dom.document.createElement("ol");
  scroller.scrollHeight = 600;
  const scroll = createOverlayScroll(scroller, content);
  scroll.schedule(); dom.flush(); assert.equal(scroller.scrollTop, 500);
  scroller.scrollTop = 150; scroller.dispatch("scroll"); assert.equal(scroll.following, false);
  scroller.scrollHeight = 800; scroll.schedule(); scroll.followLatest(); dom.flush(); assert.equal(scroller.scrollTop, 150);
  scroll.followLatest(true); dom.flush(); assert.equal(scroller.scrollTop, 700);
  scroller.dispatch("wheel", { deltaY: -20 }); assert.equal(scroll.following, false);
  scroller.scrollTop = 650; scroller.dispatch("scroll"); // movement up remains stopped
  scroller.scrollTop = 680; scroller.dispatch("scroll"); assert.equal(scroll.following, true);
  content.dispatch("click", { target: { closest: () => ({}) } }); assert.equal(scroll.following, false);
  scroll.destroy();
  assert.ok(dom.observers.every(observer => observer.disconnected));
  assert.ok([...scroller.listeners.values(), ...content.listeners.values()].every(callbacks => callbacks.size === 0));
  scroll.followLatest(true); assert.equal(dom.pending, 0);
});

test("touch and keyboard upward reading cancel queued overlay scrolling", () => {
  const dom = createDom(), scroller = dom.host, content = dom.document.createElement("ol");
  scroller.scrollHeight = 600;
  const scroll = createOverlayScroll(scroller, content);
  scroll.schedule(); assert.equal(dom.pending, 1);
  scroller.dispatch("keydown", { key: "PageUp" }); assert.equal(dom.pending, 0);
  scroll.followLatest(true);
  scroller.dispatch("touchstart", { touches: [{ clientY: 10 }] });
  scroller.dispatch("touchmove", { touches: [{ clientY: 30 }] });
  assert.equal(scroll.following, false); assert.equal(dom.pending, 0);
  scroll.destroy();
});
