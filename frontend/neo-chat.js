/** NEO-RETRO free conversation with a transparent chat overlay. */
import { TEAM_API } from './neo-config.mjs?v=20261126-team-api1';
import { createTeamApiClient } from './neo-team-client.mjs?v=20261126-embedding1';
import { createConversationStore, buildApiMessages } from './neo-conversation.mjs?v=20261126-embedding1';
import { renderEmbeddingStatus } from './neo-embedding.mjs';
import { renderCitedAnswer, renderMarkdown, createOverlayScroll } from './neo-chat-render.mjs';
import { MATE_PROFILES, getMateProfile } from './mate-content.mjs';
import { guideOf } from './neo-dex-view.mjs';
import { typeDialogue } from './dialogue.mjs';
import { actor, sceneBackground, platformImage, setSpriteManifest } from './neo-scenery.mjs';

const $ = id => document.getElementById(id);
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
const small = matchMedia('(max-width: 560px)');
const FACE = id => `assets/neo/mates/${guideOf(id).mateId}-pixel.png`;
const PERSONA = Object.freeze({ P1: { letter: 'A', level: 'beginner' }, P2: { letter: 'B', level: 'novice' }, P3: { letter: 'C', level: 'expert' } });
const PIKACHU_LINE = '난 피카츄야! 만나서 반가워! 누구랑 같이 시작할래?';
let api;
let db;
let confirmReset;
const state = { personaId: null, choosing: true, messages: new Map(), drafts: new Map(), requests: new Map(), resets: new Map(), suggestions: null, selection: 0, storageReady: false, ready: false, homeAnimation: null, animations: new Set(), lastRequestCount: null };
const motionOff = () => reducedMotion.matches || document.body.dataset.motion === 'off';
const profile = () => getMateProfile(state.personaId);
const messages = id => state.messages.get(id) ?? [];
const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
const button = (text, action, cls = 'nx-link-button') => { const b = el('button', cls, text); b.type = 'button'; b.addEventListener('click', action); return b; };
const face = (id, cls = 'nx-face') => { const n = el('img', cls); n.src = FACE(id); n.alt = ''; n.width = 40; n.height = 40; return n; };
const scroll = createOverlayScroll($('nx-chat-scroll'), $('nx-chat-messages'), { reducedMotion });
const announce = text => { $('nx-announce').textContent = text; };
function upsert(record) { const all = messages(record.persona_id); const at = all.findIndex(m => m.message_id === record.message_id); if (at < 0) all.push(record); else all[at] = record; state.messages.set(record.persona_id, all); }
function storageError() { state.storageReady = false; $('nx-storage-note').textContent = '대화를 브라우저에 저장하지 못했어요. 저장소 접근을 확인한 뒤 새로고침해 주세요.'; updateBusy(); }
function errorText(error) {
  if (error.kind === 'config') return '팀 API 연결 대기 중이에요. 서버 주소와 경로가 확인되면 답변을 요청할 수 있어요.';
  if (error.name === 'AbortError') return '요청이 중단됐어요. 같은 질문으로 다시 시도할 수 있어요.';
  if (error.kind === 'timeout') return '응답을 기다리는 시간이 길어졌어요. 다시 시도해 주세요.';
  if (error.kind === 'network') return '서버에 연결하지 못했어요. 네트워크와 서버의 연결 허용 설정을 확인해 주세요.';
  if (error.kind === 'validation') return '질문 또는 대화 기록이 API의 입력 규칙에 맞지 않아요. 입력 길이와 내용을 확인해 주세요.';
  if (error.kind === 'format') return '서버 응답 형식을 확인하지 못했어요. 다시 시도해 주세요.';
  return `답변을 가져오지 못했어요${error.httpStatus ? ` (HTTP ${error.httpStatus})` : ''}. 다시 시도해 주세요.`;
}
function updateBusy() {
  const resetting = state.resets.has(state.personaId);
  const busy = !!state.requests.get(state.personaId) || resetting;
  $('nx-home-form').setAttribute('aria-busy', String(busy));
  $('nx-home-form').querySelector('[type="submit"]').disabled = !state.ready || !state.storageReady || busy;
  $('nx-home-input').disabled = !state.storageReady || resetting;
  $('nx-reset-chat').disabled = !state.ready || !state.storageReady || resetting;
  document.querySelectorAll('#nx-home-options button').forEach(b => { b.disabled = busy; });
  document.querySelectorAll('.nx-chat-retry').forEach(b => { b.disabled = busy || !state.storageReady; });
}
function renderUsers() {
  $('nx-users').replaceChildren(...MATE_PROFILES.map(p => {
    const card = button('', () => selectUser(p.id), 'nx-user');
    card.dataset.persona = p.id; card.setAttribute('aria-pressed', String(p.id === state.personaId));
    card.setAttribute('aria-label', `${p.name}, ${p.subtitle}. 메이트 ${p.mateName}와 시작`);
    const body = el('span', 'nx-user-body'); body.append(el('span', 'nx-user-name', p.name), el('span', 'nx-user-sub', p.subtitle), el('span', 'nx-user-line', `“${p.description}”`));
    const mate = el('span', 'nx-user-mate'); mate.append(face(p.id), el('span', '', `메이트 ${p.mateName}`)); card.append(body, mate);
    if (p.id === state.personaId) card.append(el('span', 'nx-user-current', '지금 함께하는 중'));
    const li = el('li'); li.append(card); return li;
  }));
}
function lockScene() {
  const visual = document.querySelector('.nx-home-visual');
  const scene = document.querySelector('.nx-home-scene');
  // Measure the original chooser layout before hiding it; never replace its live scene.
  visual.style.setProperty('--nx-visual-height', `${visual.getBoundingClientRect().height}px`);
  visual.dataset.locked = 'true';
  visual.style.setProperty('--nx-chat-height', `${scene.getBoundingClientRect().height - 2 * parseFloat(getComputedStyle(scene).borderTopWidth)}px`);
}
function renderHome() {
  const p = profile(), picking = state.choosing || !p;
  $('home').dataset.chat = picking ? 'off' : 'on';
  $('nx-chooser').hidden = !picking; $('nx-start').hidden = picking; $('nx-chat-overlay').hidden = picking;
  $('nx-who').hidden = !p;
  if (p) { $('nx-who-face').src = FACE(p.id); $('nx-who-user').textContent = `${p.name} · ${p.subtitle}`; $('nx-who-mate').textContent = p.mateName; }
  if (picking) {
    state.homeAnimation?.cancel(); $('nx-home-speaker').textContent = '피카츄'; $('nx-home-face').src = 'assets/neo/sprites/25.png';
    const box = document.querySelector('.nx-home-dialogue'); box.classList.remove('is-done');
    state.homeAnimation = typeDialogue($('nx-home-line'), PIKACHU_LINE, { instant: motionOff(), onComplete: () => box.classList.add('is-done') });
    return;
  }
  $('nx-picked-face').src = FACE(p.id); $('nx-picked-user').textContent = `${PERSONA[p.id].letter} · ${p.name} · ${p.subtitle}`;
  $('nx-picked-mate').textContent = `메이트 ${p.mateName}와 함께해요`; $('nx-home-label').textContent = `${p.mateName}에게 물어보기`;
  $('nx-home-input').placeholder = `${p.mateName}에게 궁금한 걸 물어봐.`;
  document.title = `${p.mateName}와 대화 · 관동도감`;
  renderThread(); updateBusy();
}
async function selectUser(id) {
  if (!state.ready || !getMateProfile(id)) return;
  if (state.choosing) { state.homeAnimation?.finish(); lockScene(); }
  if (state.personaId) state.drafts.set(state.personaId, $('nx-home-input').value);
  if (state.personaId !== id) {
    state.lastRequestCount = null;
    $('nx-context-note').textContent = '대화는 이 브라우저에 저장돼요. 답변에는 최근 대화 일부가 전달돼요.';
  }
  state.suggestions?.abort(); state.selection++; state.personaId = id; state.choosing = false;
  for (const animation of state.animations) animation.cancel(); state.animations.clear();
  $('nx-home-input').value = state.drafts.get(id) ?? ''; $('nx-home-note').textContent = ''; autoGrow();
  renderUsers(); renderHome(); autoGrow(); scroll.followLatest(true);
  $('nx-picked-user').focus({ preventScroll: true }); announce(`${PERSONA[id].letter} · ${profile().name}, 메이트 ${profile().mateName}와 대화를 시작해요.`);
  await loadSuggestions(id, state.selection);
}
function chooseAgain() {
  if (state.personaId) state.drafts.set(state.personaId, $('nx-home-input').value);
  state.selection++; state.suggestions?.abort(); state.choosing = true;
  for (const animation of state.animations) animation.cancel(); state.animations.clear();
  renderUsers(); renderHome();
  (document.querySelector('.nx-user[aria-pressed="true"]') ?? document.querySelector('.nx-user'))?.focus({ preventScroll: true });
}
async function resetConversation() {
  const p = profile();
  if (!p || state.choosing || !state.ready || !state.storageReady || state.resets.has(p.id)) return;
  if (confirmReset(`${p.name}의 대화를 모두 지울까요? 이 브라우저에 저장된 ${p.name}의 대화만 삭제되며 되돌릴 수 없어요.`) !== true) return;
  const id = p.id;
  let release;
  let cleared = false;
  state.resets.set(id, new Promise(resolve => { release = resolve; }));
  updateBusy();
  try {
    await db.clearPersona(id);
    // Invalidate before abort so neither a late success nor its catch can save rows again.
    const pending = state.requests.get(id);
    state.requests.delete(id); pending?.abort();
    state.messages.set(id, []); state.drafts.delete(id);
    cleared = true;
    if (state.personaId === id && !state.choosing) {
      for (const animation of state.animations) animation.cancel(); state.animations.clear();
      $('nx-chat-messages').replaceChildren(); $('nx-home-input').value = ''; autoGrow();
      $('nx-home-note').textContent = ''; state.lastRequestCount = null;
      $('nx-context-note').textContent = '대화는 이 브라우저에 저장돼요. 답변에는 최근 대화 일부가 전달돼요.';
      renderThread(); scroll.followLatest(true);
      announce(`${p.name}의 대화를 리셋했어요. ${p.mateName}와 새 대화를 시작해 보세요.`);
    }
  } catch {
    if (state.personaId === id && !state.choosing) {
      $('nx-home-note').textContent = '대화를 지우지 못했어요. 기존 대화는 유지됩니다. 다시 시도해 주세요.';
      announce($('nx-home-note').textContent);
    }
  } finally {
    state.resets.delete(id); release(); updateBusy();
    if (cleared && state.personaId === id && !state.choosing) $('nx-home-input').focus({ preventScroll: true });
  }
}
async function requestIsCurrent(id, controller) {
  // A reset waits for existing IDB writes; later writes wait for its outcome.
  // On deletion failure the original request remains valid and can finish normally.
  await state.resets.get(id);
  return state.requests.get(id) === controller;
}
async function loadSuggestions(id, selection) {
  const controller = new AbortController(); state.suggestions = controller;
  $('nx-home-options').replaceChildren(); $('nx-suggestions-note').replaceChildren(el('span', '', '추천 질문을 불러오는 중이에요…'));
  try {
    const result = await api.getSuggestions(PERSONA[id].level, { signal: controller.signal });
    if (state.selection !== selection || state.personaId !== id || state.choosing) return;
    $('nx-suggestions-note').textContent = result.suggestions.length ? '' : '추천 질문이 아직 없어요. 궁금한 내용을 직접 입력해 주세요.';
    $('nx-home-options').replaceChildren(...result.suggestions.map(s => {
      const li = el('li'); const b = button(s.text, () => { if (!state.requests.has(id)) submitQuestion(s.text); }, 'nx-option'); b.dataset.suggestionId = s.id; li.append(b); return li;
    })); updateBusy();
  } catch (error) {
    if (state.selection !== selection || state.personaId !== id || controller.signal.aborted || state.choosing) return;
    $('nx-suggestions-note').replaceChildren(el('span', '', error.kind === 'config' ? '추천 질문 API 연결 대기 중이에요. 자유 질문을 입력할 수 있어요.' : '추천 질문을 불러오지 못했어요. 자유 질문을 계속할 수 있어요.'), button('다시 불러오기', () => loadSuggestions(id, selection)));
  }
}
function newRecord(role, content, p) {
  return { conversation_id: `kanto-${p.id}`, persona_id: p.id, mate_id: guideOf(p.id).mateId, message_id: crypto.randomUUID(), role, content, created_at: new Date().toISOString(), mode: null, sources: [], request_status: 'pending' };
}
function renderThread(animateId = null) {
  const p = profile(); if (!p || state.choosing) return;
  const list = $('nx-chat-messages');
  const samePersona = list.dataset.persona === p.id;
  if (!samePersona) { list.replaceChildren(); list.dataset.persona = p.id; }
  const previousTop = $('nx-chat-scroll').scrollTop;
  const following = scroll.following;
  const rows = new Map([...list.querySelectorAll('[data-message-id]')].map(n => [n.dataset.messageId, n]));
  if (!list.querySelector('[data-greeting]')) {
  const greeting = el('li', 'nx-chat-message'); greeting.dataset.role = 'assistant';
  greeting.dataset.greeting = 'true';
  const body = el('div', 'nx-chat-body'); body.append(el('span', 'nx-chat-name', p.mateName));
  const bubble = el('div', 'nx-chat-bubble'); bubble.append(el('p', 'nx-chat-text', p.greeting)); body.append(bubble); greeting.append(face(p.id, 'nx-chat-avatar'), body); list.append(greeting);
  }
  for (const m of messages(p.id)) {
    const key = `${m.request_status}|${m.content}|${m.error_message ?? ''}|${m.mode ?? ''}|${JSON.stringify(m.embedding ?? null)}`;
    const previous = rows.get(m.message_id);
    if (previous?.dataset.renderKey === key) continue;
    const li = el('li', 'nx-chat-message'); li.dataset.role = m.role; li.dataset.messageId = m.message_id;
    li.dataset.renderKey = key;
    const content = el('div', 'nx-chat-body'); const name = m.role === 'user' ? `${PERSONA[p.id].letter} · ${p.name}` : p.mateName;
    content.append(el('span', 'nx-chat-name', name)); const box = el('div', 'nx-chat-bubble'); const text = el('p', 'nx-chat-text'); box.append(text);
    const reveal = () => renderCitedAnswer(text, m.content, m.sources, source => openDocument(box, m, source));
    if (m.role === 'assistant') {
      if (animateId === m.message_id && !motionOff() && !document.hidden) {
        text.dataset.fullAnswer = m.content;
        const a = typeDialogue(text, m.content, { onComplete: () => { reveal(); state.animations.delete(a); scroll.schedule(); } }); state.animations.add(a);
        box.append(button('답변 전체 보기', () => a.finish(), 'nx-link-button nx-chat-finish'));
      } else reveal();
      const status = el('p', 'nx-chat-status'); renderEmbeddingStatus(status, m); box.append(status);
      const sources = el('ol', `nx-chat-sources${animateId === m.message_id ? ' is-revealing' : ''}`);
      const seen = new Set();
      for (const s of m.sources) {
        const key = `${s.ref}|${s.chunk_id}|${s.source_ref_id}`; if (seen.has(key)) continue; seen.add(key);
        const row = el('li'); row.style.setProperty('--source-index', sources.children.length);
        const b = button(`[${s.ref}] ${s.chunk_id}`, () => openDocument(box, m, s), 'nx-chat-source'); b.append(el('small', '', s.source_ref_id)); row.append(b); sources.append(row);
      }
      if (sources.children.length) box.append(sources); else box.append(el('p', 'nx-chat-status', '제공된 출처 없음'));
    } else {
      text.textContent = m.content;
      if (m.request_status === 'pending') box.append(el('p', 'nx-chat-status', '답변을 기다리고 있어요…'));
      if (m.request_status === 'failed') {
        box.append(el('p', 'nx-chat-status nx-chat-error', m.error_message || '이 요청이 완료되지 않았어요. 다시 시도할 수 있어요.'));
        box.append(button('다시 보내기', () => submitQuestion(m.content, m), 'nx-link-button nx-chat-retry'));
      }
    }
    const time = el('time', 'nx-chat-time', new Intl.DateTimeFormat('ko-KR', { hour: '2-digit', minute: '2-digit' }).format(new Date(m.created_at))); time.dateTime = m.created_at; box.append(time);
    content.append(box); if (m.role === 'assistant') li.append(face(p.id, 'nx-chat-avatar')); li.append(content);
    if (previous) previous.replaceWith(li); else list.append(li);
  }
  if (samePersona && !following) { $('nx-chat-scroll').scrollTop = previousTop; scroll.stop(); }
  scroll.schedule(); updateBusy();
}
async function openDocument(box, message, source) {
  scroll.stop();
  const existing = [...box.querySelectorAll('.nx-chat-document')].find(n => n.dataset.sourceId === source.source_ref_id);
  if (existing) { existing.hidden = !existing.hidden; return; }
  const selection = state.selection;
  const panel = el('section', 'nx-chat-document'); panel.dataset.sourceId = source.source_ref_id;
  panel.append(el('h3', '', `원문 문서 · ${source.source_ref_id}`), button('닫기', () => { panel.hidden = true; }));
  const status = el('p', 'nx-chat-status', '원문을 불러오는 중이에요…'); status.setAttribute('role', 'status'); const content = el('div', 'nx-document-content');
  panel.append(status, content); box.append(panel);
  async function load() {
    status.textContent = '원문을 불러오는 중이에요…'; content.replaceChildren();
    try {
      const doc = await api.getDocument(source.source_ref_id);
      if (selection !== state.selection || state.personaId !== message.persona_id || !panel.isConnected) return;
      status.textContent = '원문 문서 전체 · 검색 청크 본문과 구분됩니다.'; renderMarkdown(content, doc.markdown);
    } catch (error) {
      if (selection !== state.selection || !panel.isConnected) return;
      status.textContent = `원문을 불러오지 못했어요${error.httpStatus ? ` (HTTP ${error.httpStatus})` : ''}.`;
      content.replaceChildren(button('원문 다시 불러오기', load));
    }
  }
  await load();
}
async function submitQuestion(value, retry = null) {
  const p = profile(); if (!p || state.choosing || !state.ready || !state.storageReady || state.requests.has(p.id) || state.resets.has(p.id)) return;
  const question = String(value ?? '').trim(); if (!question) return;
  const controller = new AbortController(); const id = p.id; const record = retry ? { ...retry, request_status: 'pending', error_message: null } : newRecord('user', question, p);
  state.requests.set(id, controller); updateBusy();
  try {
    const payload = buildApiMessages(messages(id), record, { maxMessages: api.maxMessages, maxContentLength: api.maxContentLength ?? Infinity });
    try { await db.save(record); } catch { if (await requestIsCurrent(id, controller)) storageError(); return; }
    if (!await requestIsCurrent(id, controller)) return;
    upsert(record);
    if (state.personaId === id && !state.choosing) {
      if (!retry) { $('nx-home-input').value = ''; state.drafts.set(id, ''); autoGrow(); }
      $('nx-home-note').textContent = ''; renderThread(); scroll.followLatest();
      $('nx-context-note').textContent = `대화는 이 브라우저에 저장돼요. 이번 요청에는 최근 ${payload.length}개 메시지가 전달돼요.`;
    }
    const result = await api.ask(payload, { signal: controller.signal });
    if (!await requestIsCurrent(id, controller)) return;
    const user = { ...record, request_status: 'completed' };
    const answer = { ...newRecord('assistant', result.answer, p), reply_to: record.message_id, request_status: 'completed', mode: result.mode, sources: result.sources,
      ...(result.embedding ? { embedding: result.embedding } : {}) };
    try { await db.saveMany([user, answer]); } catch {
      if (!await requestIsCurrent(id, controller)) return;
      // Keep the received answer visible, but never claim it was saved.
      upsert(user); upsert(answer); storageError();
      if (state.personaId === id && !state.choosing) renderThread();
      return;
    }
    if (!await requestIsCurrent(id, controller)) return;
    upsert(user); upsert(answer);
    if (state.personaId === id && !state.choosing) { renderThread(answer.message_id); announce(`${p.mateName}의 답변이 도착했어요. ${result.mode} 모드, 출처 ${result.sources.length}개.`); }
  } catch (error) {
    if (!await requestIsCurrent(id, controller)) return;
    const failed = { ...record, request_status: 'failed', error_message: errorText(error) };
    try { await db.save(failed); if (!await requestIsCurrent(id, controller)) return; upsert(failed); }
    catch { if (!await requestIsCurrent(id, controller)) return; storageError(); }
    if (state.personaId === id && !state.choosing) { renderThread(); $('nx-home-note').textContent = failed.error_message; announce(failed.error_message); }
  } finally { if (state.requests.get(id) === controller) state.requests.delete(id); updateBusy(); }
}
function autoGrow() { const input = $('nx-home-input'); input.style.height = 'auto'; const height = Math.max(input.scrollHeight + 4, 52); input.style.height = `${Math.min(height, 160)}px`; input.style.overflowY = height > 160 ? 'auto' : 'hidden'; }
function route() { if (location.hash !== '#home') history.replaceState(null, '', `${location.pathname}${location.search}#home`); document.body.dataset.view = 'home'; }
async function initialize() {
  route(); document.querySelectorAll('.nx-scene-bg').forEach(n => { n.style.backgroundImage = sceneBackground(); }); document.documentElement.style.setProperty('--platform', platformImage());
  $('nx-mode').textContent = api.ready ? '팀 API' : 'API · 연결 대기'; $('nx-mode').title = api.ready ? '답변 모드는 각 응답에 표시돼요.' : '팀 API 주소와 경로가 필요해요.';
  $('nx-foot-mode').textContent = api.ready ? 'RED/BLUE · 답변 모드는 서버 응답에 표시됩니다.' : '팀 API 연결 대기'; document.body.dataset.mode = 'api';
  $('nx-home-input').removeAttribute('maxlength'); if (api.maxContentLength) $('nx-home-input').maxLength = api.maxContentLength;
  $('nx-home-form').addEventListener('submit', event => { event.preventDefault(); submitQuestion($('nx-home-input').value); });
  $('nx-home-input').addEventListener('input', () => { autoGrow(); $('nx-home-note').textContent = ''; });
  $('nx-home-input').addEventListener('keydown', event => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229) { event.preventDefault(); $('nx-home-form').requestSubmit(); } });
  $('nx-change-user').addEventListener('click', chooseAgain); $('nx-rechoose').addEventListener('click', chooseAgain); $('nx-chat-latest').addEventListener('click', () => scroll.followLatest(true));
  $('nx-reset-chat').addEventListener('click', resetConversation);
  $('nx-motion').addEventListener('click', () => { const off = document.body.dataset.motion !== 'off'; document.body.dataset.motion = off ? 'off' : 'on'; $('nx-motion').setAttribute('aria-pressed', String(off)); $('nx-motion').setAttribute('aria-label', off ? '움직임 다시 켜기' : '움직임 멈추기'); if (off) { state.homeAnimation?.finish(); for (const a of state.animations) a.finish(); } });
  window.addEventListener('hashchange', route); window.addEventListener('popstate', route);
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) return;
    // Shared typeDialogue cancels when hidden; restore exact saved answers on return.
    const p = profile(); if (!p || state.choosing) return;
    for (const text of document.querySelectorAll('[data-full-answer]')) {
      const m = messages(p.id).find(row => row.message_id === text.closest('[data-message-id]').dataset.messageId);
      if (m) renderCitedAnswer(text, m.content, m.sources, source => openDocument(text.closest('.nx-chat-bubble'), m, source));
      delete text.dataset.fullAnswer;
    }
  });
  const manifest = await fetch('assets/neo/sprites/manifest.json').then(r => r.ok ? r.json() : {}).catch(() => ({})); setSpriteManifest(manifest);
  $('nx-home-stage').append(actor(25, { left: '50%', bottom: small.matches ? '10%' : '24%', scale: small.matches ? 2 : 4, focus: true }));
  try {
    for (const id of Object.keys(PERSONA)) { await db.recoverPending(id); state.messages.set(id, await db.load(id)); }
    state.storageReady = true;
  } catch { storageError(); }
  state.ready = true; renderUsers(); renderHome(); await document.fonts.ready;
  if (!small.matches) lockScene();
  // Re-measure only after an actual viewport change. Message growth never resizes scenery.
  let width = window.innerWidth;
  window.addEventListener('resize', () => {
    if (!state.ready) return;
    if (window.innerWidth === width) return; width = window.innerWidth;
    const choosing = state.choosing; const chooser = $('nx-chooser'), start = $('nx-start'), visual = document.querySelector('.nx-home-visual');
    delete visual.dataset.locked; chooser.hidden = false; start.hidden = true; $('home').dataset.chat = 'off';
    const old = document.querySelector('#nx-home-stage .nx-sprite-wrap'); if (!old) return; const scale = small.matches ? 2 : 4;
    old.style.setProperty('--s', scale); const bbox = manifest[25]?.bbox ?? [0, 0, 64, 64]; old.style.setProperty('--dx', `${(32 - (bbox[0] + bbox[2]) / 2) * scale}px`); old.style.setProperty('--dy', `${(64 - bbox[3]) * scale}px`); document.querySelector('#nx-home-stage .nx-actor').style.bottom = small.matches ? '10%' : '24%';
    state.homeAnimation?.finish(); lockScene(); state.choosing = choosing; renderHome();
  });
  updateBusy(); document.dispatchEvent(new CustomEvent('neo-chat-ready'));
}
export async function startNeoChat({ client = createTeamApiClient({ config: TEAM_API }), store = createConversationStore(), confirmReset: confirm = message => window.confirm(message) } = {}) {
  api = client; db = store; confirmReset = confirm;
  try { await initialize(); } catch { $('nx-load-note').textContent = '화면을 불러오지 못했어요. 새로고침해 주세요.'; }
}
