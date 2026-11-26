/** Local presentation only: safe text animation and user-triggered browser speech. */
const activeDialogues = new WeakMap();
let activeSpeech = null;
const TYPING_INTERVAL_MS = 20;

function graphemes(text) {
  if (typeof Intl?.Segmenter === "function") {
    return [...new Intl.Segmenter("ko", { granularity: "grapheme" }).segment(text)]
      .map(part => ({ text: part.segment, start: part.index, end: part.index + part.segment.length }));
  }
  let offset = 0;
  return Array.from(text, part => {
    const segment = { text: part, start: offset, end: offset + part.length };
    offset = segment.end; return segment;
  });
}

function prepareText(text, keywords) {
  const segments = graphemes(text);
  const boundaries = new Set([0, ...segments.map(segment => segment.end)]);
  const words = [...new Set(keywords.map(word => String(word)).filter(Boolean))]
    .sort((left, right) => right.length - left.length);
  const ranges = [];
  for (const word of words) {
    let cursor = 0;
    while (cursor <= text.length - word.length) {
      const start = text.indexOf(word, cursor);
      if (start < 0) break;
      const end = start + word.length;
      if (boundaries.has(start) && boundaries.has(end) && !ranges.some(range => start < range.end && end > range.start)) {
        ranges.push({ start, end });
      }
      cursor = start + word.length;
    }
  }
  ranges.sort((left, right) => left.start - right.start);
  let rangeIndex = 0;
  return segments.map(segment => {
    while (ranges[rangeIndex] && segment.start >= ranges[rangeIndex].end) rangeIndex++;
    const range = ranges[rangeIndex];
    return { ...segment, emphasis: range && segment.start >= range.start && segment.end <= range.end ? rangeIndex + 1 : 0 };
  });
}

/**
 * The host's aria-live policy belongs to the caller. Only aria-busy is changed.
 * Call cancel before hiding a view; hidden/detached hosts also stop on the next tick.
 * A replacement call on the same host automatically cancels the old timer.
 */
export function typeDialogue(host, text, { keywords = [], instant = false, onComplete } = {}) {
  if (!host?.ownerDocument?.createTextNode || !host.replaceChildren || !host.classList || !host.setAttribute) {
    throw new TypeError("A DOM host is required");
  }
  if (!Array.isArray(keywords)) throw new TypeError("keywords must be an array");
  activeDialogues.get(host)?.cancel();
  const document = host.ownerDocument;
  const segments = prepareText(String(text ?? ""), keywords);
  let timer, cursor = 0, stopped = false, currentText = null, currentEmphasis = -1;
  host.replaceChildren();
  host.classList.add("is-typing"); host.setAttribute("aria-busy", "true");

  function cleanUp() {
    clearTimeout(timer);
    host.classList.remove("is-typing"); host.setAttribute("aria-busy", "false");
    document.removeEventListener?.("visibilitychange", handleVisibility);
    if (activeDialogues.get(host) === controller) activeDialogues.delete(host);
  }
  function appendSegment() {
    const segment = segments[cursor++];
    if (segment.emphasis !== currentEmphasis) {
      currentEmphasis = segment.emphasis; currentText = document.createTextNode("");
      if (segment.emphasis) {
        const strong = document.createElement("strong"); strong.append(currentText); host.append(strong);
      } else host.append(currentText);
    }
    currentText.textContent += segment.text;
  }
  function complete() {
    stopped = true; cleanUp();
    if (typeof onComplete === "function") onComplete();
  }
  function cancel() {
    if (stopped) return;
    stopped = true; cleanUp();
  }
  function finish() {
    if (stopped) return;
    clearTimeout(timer);
    while (cursor < segments.length) appendSegment();
    complete();
  }
  function tick() {
    if (stopped) return;
    if (host.isConnected === false || host.closest?.("[hidden]") || document.hidden) { cancel(); return; }
    appendSegment();
    if (cursor >= segments.length) complete(); else timer = setTimeout(tick, TYPING_INTERVAL_MS);
  }
  function handleVisibility() { if (document.hidden) cancel(); }
  const controller = { finish, cancel };
  activeDialogues.set(host, controller);
  document.addEventListener?.("visibilitychange", handleVisibility);
  if (instant || segments.length === 0) finish(); else timer = setTimeout(tick, TYPING_INTERVAL_MS);
  return controller;
}

/** Call only from a user's explicit speech action. No voice download or external API. */
export function speakDialogue(text, { onEnd, onError } = {}) {
  const synthesis = globalThis.speechSynthesis, Utterance = globalThis.SpeechSynthesisUtterance;
  const unavailable = reason => ({ supported: false, reason, cancel() {} });
  if (!synthesis?.getVoices || !synthesis.speak || typeof Utterance !== "function") return unavailable("speech-unavailable");
  let voice;
  try { voice = synthesis.getVoices().find(item => /^ko(?:-|_|$)/i.test(item.lang)); }
  catch { return unavailable("voices-unavailable"); }
  if (!voice) return unavailable("korean-voice-unavailable");
  const value = String(text ?? "");
  if (!value.trim()) return unavailable("empty-text");
  activeSpeech?.cancel();
  const utterance = new Utterance(value);
  utterance.lang = "ko-KR"; utterance.voice = voice;
  let active = true;
  function cleanUp() { active = false; if (activeSpeech === controller) activeSpeech = null; }
  const controller = {
    supported: true,
    cancel() {
      if (!active) return;
      cleanUp(); utterance.onend = null; utterance.onerror = null;
      synthesis.cancel?.();
    },
  };
  utterance.onend = event => { if (active) { cleanUp(); if (typeof onEnd === "function") onEnd(event); } };
  utterance.onerror = event => { if (active) { cleanUp(); if (typeof onError === "function") onError(event); } };
  activeSpeech = controller;
  try { synthesis.speak(utterance); }
  catch (error) {
    cleanUp(); if (typeof onError === "function") onError(error);
    return unavailable("speech-error");
  }
  return controller;
}
