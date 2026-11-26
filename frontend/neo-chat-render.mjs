/** Safe, dependency-free presentation for API answers and source documents. */

function text(host, value) { host.append(host.ownerDocument.createTextNode(String(value))); }
function element(document, tag, value) {
  const node = document.createElement(tag);
  if (value !== undefined) node.textContent = String(value);
  return node;
}

/** Only explicit HTTP(S) document links are navigable. No relative or data URLs. */
export function safeDocumentUrl(value) {
  if (typeof value !== "string") return null;
  const candidate = value.trim();
  if (!/^https?:\/\//iu.test(candidate) || /[\u0000-\u0020\u007f]/u.test(candidate)) return null;
  try {
    const url = new URL(candidate);
    if (!["https:", "http:"].includes(url.protocol) || !url.hostname || url.username || url.password) return null;
    return url.href;
  } catch { return null; }
}

/** Numbering is resolved against this answer only. Unknown references stay text. */
export function renderCitedAnswer(host, answer, sources = [], onOpenSource = () => {}) {
  const byRef = new Map();
  for (const source of sources) {
    if (Number.isInteger(source?.ref) && source.ref > 0 && !byRef.has(source.ref)) byRef.set(source.ref, source);
  }
  host.replaceChildren();
  const value = String(answer ?? "");
  let cursor = 0;
  for (const match of value.matchAll(/\[(\d+)\]/gu)) {
    text(host, value.slice(cursor, match.index));
    const source = byRef.get(Number(match[1]));
    if (source) {
      const button = element(host.ownerDocument, "button", match[0]);
      button.type = "button";
      button.className = "nx-citation";
      button.setAttribute("aria-label", `출처 ${source.ref} 원문 보기`);
      button.addEventListener("click", () => onOpenSource(source));
      host.append(button);
    } else text(host, match[0]);
    cursor = match.index + match[0].length;
  }
  text(host, value.slice(cursor));
}

function closingParen(value, start) {
  let depth = 1;
  for (let i = start; i < value.length; i++) {
    if (value[i] === "\\") { i++; continue; }
    if (value[i] === "(") depth++;
    if (value[i] === ")" && --depth === 0) return i;
  }
  return -1;
}

function inline(host, value, depth = 0) {
  if (depth > 8) { text(host, value); return; }
  let cursor = 0, plainStart = 0;
  const flush = end => { if (end > plainStart) text(host, value.slice(plainStart, end)); };
  while (cursor < value.length) {
    const char = value[cursor];
    if (char === "\\" && cursor + 1 < value.length && /[\\`*_[\]{}()#!|>]/u.test(value[cursor + 1])) {
      flush(cursor); text(host, value[cursor + 1]); cursor += 2; plainStart = cursor; continue;
    }
    if (char === "`") {
      const end = value.indexOf("`", cursor + 1);
      if (end > cursor + 1) {
        flush(cursor); host.append(element(host.ownerDocument, "code", value.slice(cursor + 1, end)));
        cursor = end + 1; plainStart = cursor; continue;
      }
    }
    const image = char === "!" && value[cursor + 1] === "[";
    if (char === "[" || image) {
      const labelStart = cursor + (image ? 2 : 1), labelEnd = value.indexOf("](", labelStart);
      if (labelEnd >= labelStart) {
        const end = closingParen(value, labelEnd + 2);
        if (end >= 0) {
          const label = value.slice(labelStart, labelEnd), href = safeDocumentUrl(value.slice(labelEnd + 2, end));
          flush(cursor);
          if (href && !image) {
            const anchor = element(host.ownerDocument, "a", label);
            anchor.setAttribute("href", href); anchor.setAttribute("target", "_blank");
            anchor.setAttribute("rel", "noopener noreferrer"); host.append(anchor);
          } else if (image) text(host, `[이미지: ${label}]`);
          else text(host, value.slice(cursor, end + 1));
          cursor = end + 1; plainStart = cursor; continue;
        }
      }
    }
    const delimiter = value.startsWith("**", cursor) ? "**" : value.startsWith("__", cursor) ? "__"
      : (char === "*" || char === "_") ? char : null;
    if (delimiter) {
      const end = value.indexOf(delimiter, cursor + delimiter.length);
      if (end > cursor + delimiter.length) {
        flush(cursor);
        const node = element(host.ownerDocument, delimiter.length === 2 ? "strong" : "em");
        inline(node, value.slice(cursor + delimiter.length, end), depth + 1); host.append(node);
        cursor = end + delimiter.length; plainStart = cursor; continue;
      }
    }
    cursor++;
  }
  flush(value.length);
}

function cells(line) {
  let value = line.trim();
  if (value.startsWith("|")) value = value.slice(1);
  if (value.endsWith("|") && !value.endsWith("\\|")) value = value.slice(0, -1);
  return value.split(/(?<!\\)\|/u).map(cell => cell.trim().replaceAll("\\|", "|"));
}
const tableDivider = line => cells(line).length > 0 && cells(line).every(cell => /^:?-{3,}:?$/u.test(cell));
const heading = line => /^(#{1,6})\s+(.+)$/u.exec(line);
const listItem = line => /^\s*(?:([-+*])|(\d+)[.)])\s+(.+)$/u.exec(line);
const fence = line => /^\s*(`{3,}|~{3,})(.*)$/u.exec(line);

/**
 * Sanitization by construction: only known Markdown elements/attributes are
 * created, raw HTML is text, image URLs never load, links pass an HTTP(S) gate.
 */
export function renderMarkdown(host, markdown) {
  host.replaceChildren();
  const document = host.ownerDocument;
  const lines = String(markdown ?? "").replace(/\r\n?/gu, "\n").split("\n");
  const appendBlock = (tag, value) => { const node = element(document, tag); inline(node, value); host.append(node); return node; };
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) { index++; continue; }
    const codeFence = fence(line);
    if (codeFence) {
      const codeLines = []; index++;
      while (index < lines.length && !(fence(lines[index])?.[1]?.[0] === codeFence[1][0] && fence(lines[index])[1].length >= codeFence[1].length)) {
        codeLines.push(lines[index++]);
      }
      if (index < lines.length) index++;
      const pre = element(document, "pre"), code = element(document, "code", codeLines.join("\n")); pre.append(code); host.append(pre); continue;
    }
    const title = heading(line);
    if (title) { appendBlock(`h${title[1].length}`, title[2].replace(/\s+#+\s*$/u, "")); index++; continue; }
    if (index + 1 < lines.length && line.includes("|") && tableDivider(lines[index + 1])) {
      const table = element(document, "table"), thead = element(document, "thead"), tbody = element(document, "tbody"), row = element(document, "tr");
      const headers = cells(line);
      for (const value of headers) { const th = element(document, "th"); th.setAttribute("scope", "col"); inline(th, value); row.append(th); }
      thead.append(row); index += 2;
      while (index < lines.length && lines[index].trim() && lines[index].includes("|")) {
        const tr = element(document, "tr"), values = cells(lines[index++]);
        for (let col = 0; col < headers.length; col++) { const td = element(document, "td"); inline(td, values[col] ?? ""); tr.append(td); }
        tbody.append(tr);
      }
      table.append(thead, tbody); host.append(table); continue;
    }
    const item = listItem(line);
    if (item) {
      const ordered = Boolean(item[2]), list = element(document, ordered ? "ol" : "ul");
      if (ordered && item[2] !== "1") list.setAttribute("start", item[2]);
      while (index < lines.length) {
        const next = listItem(lines[index]);
        if (!next || Boolean(next[2]) !== ordered) break;
        const li = element(document, "li"); inline(li, next[3]); list.append(li); index++;
      }
      host.append(list); continue;
    }
    if (/^\s*>\s?/u.test(line)) {
      const quote = [];
      while (index < lines.length && /^\s*>\s?/u.test(lines[index])) quote.push(lines[index++].replace(/^\s*>\s?/u, ""));
      appendBlock("blockquote", quote.join("\n")); continue;
    }
    if (/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/u.test(line)) { host.append(element(document, "hr")); index++; continue; }
    const paragraph = [line]; index++;
    while (index < lines.length && lines[index].trim() && !heading(lines[index]) && !listItem(lines[index]) && !fence(lines[index])
      && !/^\s*>/u.test(lines[index]) && !(lines[index].includes("|") && index + 1 < lines.length && tableDivider(lines[index + 1]))) {
      paragraph.push(lines[index++]);
    }
    appendBlock("p", paragraph.join("\n"));
  }
}

/** Follow only the independently scrolling overlay; never scroll the page. */
export function createOverlayScroll(scroller, content, { reducedMotion } = {}) {
  const view = scroller.ownerDocument.defaultView ?? globalThis;
  const requestFrame = view.requestAnimationFrame?.bind(view) ?? (callback => setTimeout(callback, 16));
  const cancelFrame = view.cancelAnimationFrame?.bind(view) ?? clearTimeout;
  let following = true, frame = 0, destroyed = false, lastTop = scroller.scrollTop, touchY = null;
  const listeners = [];
  const nearEnd = () => scroller.scrollHeight - scroller.clientHeight - scroller.scrollTop <= 72;
  const listen = (target, name, callback, options) => {
    target.addEventListener(name, callback, options); listeners.push(() => target.removeEventListener(name, callback, options));
  };
  function stop() { following = false; if (frame) cancelFrame(frame); frame = 0; }
  function schedule() {
    if (destroyed || !following || frame) return;
    frame = requestFrame(() => {
      frame = 0;
      if (destroyed || !following) return;
      const top = Math.max(0, scroller.scrollHeight - scroller.clientHeight);
      scroller.scrollTo({ top, behavior: "instant" }); lastTop = scroller.scrollTop;
    });
  }
  function followLatest(force = false) {
    if (destroyed) return;
    if (force) following = true;
    if (following) schedule();
  }
  listen(scroller, "scroll", () => {
    const top = scroller.scrollTop;
    if (top < lastTop - 2) stop();
    else if (top > lastTop && nearEnd()) following = true;
    lastTop = top;
  }, { passive: true });
  listen(scroller, "wheel", event => { if (event.deltaY < 0 && !event.ctrlKey) stop(); }, { passive: true });
  listen(scroller, "touchstart", event => { touchY = event.touches.length === 1 ? event.touches[0].clientY : null; }, { passive: true });
  listen(scroller, "touchmove", event => {
    if (touchY === null || event.touches.length !== 1) return;
    const y = event.touches[0].clientY; if (y > touchY + 3) stop(); touchY = y;
  }, { passive: true });
  listen(scroller, "keydown", event => {
    if (["ArrowUp", "PageUp", "Home"].includes(event.key) || (event.key === " " && event.shiftKey)) stop();
  });
  listen(content, "click", event => { if (event.target.closest?.("summary, .nx-citation, [data-source-ref]")) stop(); });
  const Resize = view.ResizeObserver ?? globalThis.ResizeObserver;
  const observer = Resize ? new Resize(schedule) : null;
  observer?.observe(content); observer?.observe(scroller);
  return {
    followLatest, schedule, stop,
    get following() { return following; },
    destroy() { destroyed = true; stop(); observer?.disconnect(); for (const remove of listeners) remove(); },
  };
}
