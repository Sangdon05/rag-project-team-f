/** Explicit test transport, isolated real IndexedDB, and the production chat controller. */
import { startNeoChat } from '../frontend/neo-chat.js?v=20261126-reset1';
import { createTeamApiClient } from '../frontend/neo-team-client.mjs';
import { createConversationStore } from '../frontend/neo-conversation.mjs';
import { getMateProfile } from '../frontend/mate-content.mjs';

const $ = id => document.getElementById(id);
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const runKey = 'kanto-neo-browser-qa-run';
let saved;
try { saved = JSON.parse(sessionStorage.getItem(runKey) || 'null'); } catch { saved = null; }
if (new URLSearchParams(location.search).has('reset')) {
  saved = null;
  const clean = new URL(location.href); clean.searchParams.delete('reset'); history.replaceState(null, '', clean);
}
const dbName = saved?.dbName || `kanto-neo-browser-qa-${Date.now()}`;
const report = saved?.report || [];
const requests = [];
const attempts = new Map();
let suggestionScenario = 'normal';
let docCalls = 0;
const store = createConversationStore({ dbName });
let rejectReset = false;
let acceptReset = true;
const resetPrompts = [];
const clearCalls = [];
const pendingResetRequests = new Map();
const pausedWrites = new Map();
const holdCommittedWrite = (question, result) => new Promise(resolve => {
  pausedWrites.set(question, { release: () => resolve(result) });
});
const controlledStore = {
  ...store,
  async save(record) {
    const result = await store.save(record);
    if ((record.request_status === 'pending' && record.content.startsWith('SAVE-PAUSE'))
        || (record.request_status === 'failed' && record.content.includes('FAILED-SAVE-PAUSE'))) {
      return holdCommittedWrite(record.content, result);
    }
    return result;
  },
  async saveMany(records) {
    const result = await store.saveMany(records);
    const question = records.find(record => record.role === 'user')?.content;
    if (question?.startsWith('SAVEMANY-PAUSE')) return holdCommittedWrite(question, result);
    return result;
  },
  async clearPersona(personaId) {
    clearCalls.push(personaId);
    if (rejectReset) throw new Error('fixture reset transaction failure');
    return store.clearPersona(personaId);
  },
};
const confirmReset = message => { resetPrompts.push(message); return acceptReset; };
const resultElement = document.createElement('pre'); resultElement.id = 'neo-qa-results'; resultElement.style.cssText = 'white-space:pre-wrap;margin:20px;padding:16px;border:2px solid #243d55;background:#f2ebdd;color:#243d55;';
const resultDetails = document.createElement('details'); resultDetails.style.margin = '12px 20px 30px';
const resultSummary = document.createElement('summary'); resultSummary.textContent = '통합 테스트 상세 결과 (테스트 응답)';
resultDetails.append(resultSummary, resultElement); document.body.append(resultDetails);
const label = document.createElement('p'); label.id = 'neo-qa-label'; label.textContent = '통합 테스트 전용 · 응답은 테스트 픽스처 · 실제 팀 API 아님';
label.style.cssText = 'position:fixed;bottom:0;left:0;z-index:20;margin:0;padding:3px 7px;background:#f2c84b;color:#243d55;border:1px solid #243d55;font:12px/1.4 sans-serif;'; document.body.append(label);
function publish(status = 'running') { document.body.dataset.qaStatus = status; resultElement.textContent = JSON.stringify({ status, dbName, testCount: report.length, results: report, requests: requests.map(({ method, pathname, body }) => ({ method, pathname, ...(body ? { body } : {}) })) }, null, 2); }
function check(name, value, detail = '') { report.push({ name, pass: Boolean(value), ...(detail ? { detail } : {}) }); publish(); if (!value) throw new Error(`${name}: ${detail}`); }
async function until(test, name, ms = 5000) { const start = performance.now(); while (!test()) { if (performance.now() - start > ms) throw new Error(`Timeout: ${name}; ${JSON.stringify({ picked: $('nx-picked-user')?.textContent, startHidden: $('nx-start')?.hidden, chooserHidden: $('nx-chooser')?.hidden, suggestions: $('nx-suggestions-note')?.textContent, requests: requests.slice(-2) })}`); await pause(20); } }
const response = (data, status = 200) => new Response(JSON.stringify(status === 200 ? { success: true, data } : { success: false, error_code: data.code, message: '테스트용 오류 응답' }), { status, headers: { 'Content-Type': 'application/json' } });
const source = { ref: 1, chunk_id: 'pokemon-095-types', source_ref_id: 'pokeapi-pokemon5' };
async function fixtureFetch(url, init) {
  const parsed = new URL(url); const body = init.body ? JSON.parse(init.body) : null;
  requests.push({ method: init.method, pathname: parsed.pathname + parsed.search, body });
  if (parsed.pathname === '/fixture/suggestions') {
    const scenario = suggestionScenario, level = parsed.searchParams.get('level');
    if (scenario === 'late') await pause(250);
    if (scenario === 'error') return response({ code: 'INTERNAL_ERROR' }, 500);
    return response({ level, suggestions: scenario === 'empty' ? [] : Array.from({ length: 4 }, (_, index) => ({ id: `${level}-${String(index + 1).padStart(2, '0')}`, text: `${level} · 테스트 추천 질문 ${index + 1}` })) });
  }
  if (parsed.pathname.startsWith('/fixture/documents/')) {
    docCalls++;
    const id = decodeURIComponent(parsed.pathname.slice('/fixture/documents/'.length));
    if (id === 'missing-doc') return response({ code: 'DOCUMENT_NOT_FOUND' }, 404);
    return response({ source_ref_id: id, markdown: '# 롱스톤 (#95)\n\n## 타입\n바위 / 땅\n\n| 기술 | 상성 |\n| --- | --- |\n| 전기쇼크 | 효과 없음 |\n\n<script>globalThis.__neoUnsafe=true</script>\n\n[차단 링크](javascript:alert(1))\n\n![외부 이미지](https://example.test/pixel.png)\n\n[공개 참고](https://example.com/reference)' });
  }
  if (parsed.pathname === '/fixture/chat') {
    const question = body.messages.at(-1).content;
    attempts.set(question, (attempts.get(question) || 0) + 1);
    const error = /^ERR(400|500|502)/u.exec(question);
    if (error && attempts.get(question) === 1) return response({ code: error[1] === '502' ? 'ANSWER_GENERATION_FAILED' : error[1] === '400' ? 'VALIDATION_ERROR' : 'INTERNAL_ERROR' }, Number(error[1]));
    if (question.startsWith('DELAY')) await pause(250);
    const mode = question.startsWith('MOCK') ? 'mock' : question.startsWith('LLM') ? 'llm' : 'rag';
    const sources = mode === 'rag' && !question.startsWith('NOEVIDENCE') ? [{ ...source, ...(question.startsWith('DOCERROR') ? { source_ref_id: 'missing-doc' } : {}) }, { ref: 2, chunk_id: 'type-chart-electric', source_ref_id: 'gen1-type-chart' }] : [];
    return response({ answer: sources.length ? '롱스톤은 바위·땅 타입이에요[1]. 전기 기술은 땅 타입에 효과가 없어요[2]. 이 답변의 근거는 아래에서 확인할 수 있어요[1].' : `${mode} 테스트 응답 · 제공된 출처가 없어요.`, mode, sources });
  }
  throw new Error(`Unexpected fixture endpoint: ${parsed.pathname}`);
}
const transport = createTeamApiClient({ config: { baseUrl: location.origin, suggestionsPath: '/fixture/suggestions', askPath: '/fixture/chat', documentPath: '/fixture/documents/{source_ref_id}', maxMessages: 20, maxContentLength: 2000, timeoutMs: 5000 }, fetchImpl: fixtureFetch });
const client = {
  ...transport,
  ask(messages, options = {}) {
    const question = messages.at(-1).content;
    if (!question.startsWith('RESET-LATE')) return transport.ask(messages, options);
    requests.push({ method: 'POST', pathname: '/fixture/chat', body: { messages } });
    return new Promise((resolve, reject) => {
      const pending = { resolve, reject, signal: options.signal, aborted: false };
      options.signal?.addEventListener('abort', () => { pending.aborted = true; }, { once: true });
      pendingResetRequests.set(question, pending);
    });
  },
};
async function select(id) {
  if ($('nx-chooser').hidden) $('nx-change-user').click();
  document.querySelector(`#nx-users button[data-persona="${id}"]`).click();
  await until(() => {
    const note = $('nx-suggestions-note').textContent;
    const settled = $('nx-home-options').children.length > 0 || note.includes('아직 없어요') || note.includes('불러오지 못했어요') || note.includes('연결 대기');
    return !$('nx-start').hidden && settled;
  }, `select ${id}`);
}
async function send(question) {
  const before = requests.filter(r => r.pathname === '/fixture/chat').length;
  $('nx-home-input').value = question; $('nx-home-input').dispatchEvent(new Event('input', { bubbles: true })); $('nx-home-form').requestSubmit();
  await until(() => requests.filter(r => r.pathname === '/fixture/chat').length > before, `send ${question}`);
  await until(() => $('nx-home-form').getAttribute('aria-busy') === 'false', `finish ${question}`);
  await pause(30);
}
const askRequests = () => requests.filter(r => r.pathname === '/fixture/chat');
const messages = () => [...document.querySelectorAll('#nx-chat-messages [data-message-id]')];
const assistants = () => messages().filter(n => n.dataset.role === 'assistant');
const greeting = () => document.querySelector('#nx-chat-messages .nx-chat-message[data-role="assistant"] .nx-chat-text')?.textContent;
async function beginResetRequest(question) {
  $('nx-home-input').value = question;
  $('nx-home-form').requestSubmit();
  await until(() => pendingResetRequests.has(question), question);
  return pendingResetRequests.get(question);
}
const lateAnswer = () => ({ answer: '늦게 도착한 테스트 응답[1]', mode: 'rag', sources: [source] });
async function requestReset(accept = true) {
  acceptReset = accept;
  const before = resetPrompts.length;
  $('nx-reset-chat').click();
  await until(() => resetPrompts.length === before + 1, 'reset confirmation');
}

async function seedContext() {
  const records = [];
  for (let pair = 0; pair < 12; pair++) {
    const userId = `context-user-${pair}`;
    records.push({ conversation_id: 'kanto-P3', persona_id: 'P3', mate_id: 'ung', message_id: userId, role: 'user', content: `이전 질문 ${pair}`, created_at: new Date(Date.UTC(2026, 10, 26, 0, pair, 0)).toISOString(), mode: null, sources: [], request_status: 'completed' });
    records.push({ conversation_id: 'kanto-P3', persona_id: 'P3', mate_id: 'ung', message_id: `context-answer-${pair}`, role: 'assistant', content: `이전 답변 ${pair}[1]`, created_at: new Date(Date.UTC(2026, 10, 26, 0, pair, 1)).toISOString(), mode: 'rag', sources: [source], request_status: 'completed', reply_to: userId });
  }
  await store.saveMany(records);
}

async function run() {
  publish();
  if (!saved) await seedContext();
  await startNeoChat({ client, store: controlledStore, confirmReset });
  document.body.dataset.motion = 'off';
  if (saved) {
    await select('P1');
    const rows = await store.load('P1');
    check('실제 페이지 새로고침 후 IndexedDB 대화 복원', rows.length === saved.expectedA && messages().length === rows.length, `saved=${saved.expectedA}, restored=${rows.length}, rendered=${messages().length}`);
    if (saved.resetRestore) {
      check('리셋 후 실제 새로고침에도 빈 대화와 기존 인사 유지', rows.length === 0 && messages().length === 0 && greeting() === getMateProfile('P1').greeting);
      check('리셋 후 새로고침에도 다른 유저 기록 유지', JSON.stringify(await store.load('P2')) === saved.otherB && JSON.stringify(await store.load('P3')) === saved.otherC);
      await send('리셋 후 새로고침 첫 질문');
      check('리셋 후 새로고침 첫 요청은 새 질문 1개', askRequests().at(-1).body.messages.length === 1);
    }
    const restoredRows = await store.load('P1');
    check('새로고침 후 출처와 mode 보존', restoredRows.some(m => m.role === 'assistant' && m.mode === 'rag' && m.sources.length === 2));
    $('nx-chat-latest').click();
    document.body.dataset.motion = 'on';
    label.textContent = `통합 테스트 ${report.filter(r => r.pass).length}/${report.length} 통과 · 테스트 픽스처 · 실제 팀 API 아님`;
    sessionStorage.setItem(runKey, JSON.stringify({ ...saved, phase: 'complete', resetRestore: false, expectedA: restoredRows.length, report })); publish(report.every(r => r.pass) ? 'passed' : 'failed');
    return;
  }

  for (const [id, level, mate] of [['P1', 'beginner', '지우'], ['P2', 'novice', '이슬이'], ['P3', 'expert', '웅이']]) {
    await select(id);
    check(`${id} 등급·메이트 매핑`, requests.at(-1).pathname === `/fixture/suggestions?level=${level}` && $('nx-picked-mate').textContent.includes(mate));
    check(`${id} API가 반환한 추천 질문 4개 모두 표시`, $('nx-home-options').querySelectorAll('button').length === 4);
  }
  check('C 기존 대화 12쌍 복원', messages().length === 24);
  await send('CONTEXT 최근 대화 범위 확인');
  const context = askRequests().at(-1).body.messages;
  check('최근 19개만 role 교대로 전송', context.length === 19 && context.every((m, i) => m.role === (i % 2 ? 'assistant' : 'user')) && context[0].content === '이전 질문 3');
  check('잘린 이전 기록까지 로컬에 보존', (await store.load('P3')).length === 26);

  await select('P1'); await send('롱스톤한테 전기쇼크 쎄?');
  const first = assistants()[0];
  check('실제 응답 구조와 출처 번호 연결', first.querySelectorAll('.nx-citation').length === 3 && first.querySelectorAll('.nx-chat-source').length === 2 && first.textContent.includes('rag'));
  check('원문은 출처를 열기 전 요청하지 않음', docCalls === 0);
  first.querySelector('.nx-citation').click();
  await until(() => first.querySelector('.nx-document-content h1'), 'source Markdown');
  check('원문 API와 Markdown·표 렌더링', docCalls === 1 && first.querySelector('.nx-document-content table') && first.querySelector('.nx-document-content').textContent.includes('바위 / 땅'));
  check('원문 HTML·위험 링크·외부 이미지 차단', !globalThis.__neoUnsafe && !first.querySelector('.nx-document-content script, .nx-document-content img, .nx-document-content [href^="javascript:"]'));
  const panel = first.querySelector('.nx-chat-document');
  first.querySelector('.nx-citation').click(); first.querySelector('.nx-citation').click();
  check('같은 원문 펼침 재사용', docCalls === 1 && !panel.hidden);

  await send('두 번째 질문도 맥락을 기억해?');
  const secondPayload = askRequests().at(-1).body;
  check('2회차에는 이전 대화 포함·assistant 출처만 제거', Object.keys(secondPayload).join() === 'messages' && secondPayload.messages.length === 3 && !/\[\d+\]/u.test(secondPayload.messages[1].content));
  check('새 답변 이후 펼친 원문 보존', panel.isConnected && !panel.hidden);
  const second = assistants().at(-1); second.querySelector('.nx-citation').click();
  await until(() => second.querySelector('.nx-document-content h1'), 'cached source');
  check('다른 답변의 같은 원문 캐시 활용', docCalls === 1);

  for (const mode of ['MOCK', 'LLM', 'NOEVIDENCE']) {
    await send(`${mode} mode 확인`);
    const row = assistants().at(-1);
    check(`${mode} 출처 없는 응답 구분`, row.textContent.includes(mode === 'MOCK' ? 'mock' : mode === 'LLM' ? 'llm' : 'rag') && row.textContent.includes('제공된 출처 없음') && row.querySelectorAll('.nx-chat-source').length === 0);
  }
  for (const status of [400, 502, 500]) {
    const question = `ERR${status} 재시도 확인`; await send(question);
    const rowsBefore = await store.load('P1'); const failed = rowsBefore.find(m => m.role === 'user' && m.content === question);
    check(`HTTP ${status} 실패 표시`, failed.request_status === 'failed' && messages().find(n => n.dataset.messageId === failed.message_id)?.textContent.includes(`HTTP ${status}`));
    document.querySelector(`[data-message-id="${failed.message_id}"] .nx-chat-retry`).click();
    await until(() => $('nx-home-form').getAttribute('aria-busy') === 'false', `retry ${status}`); await pause(20);
    const retried = await store.load('P1');
    check(`HTTP ${status} 재시도 동일 질문 ID·중복 방지`, retried.filter(m => m.role === 'user' && m.content === question).length === 1 && retried.find(m => m.message_id === failed.message_id).request_status === 'completed');
  }

  await send('DOCERROR 없는 원문 확인');
  const badDoc = assistants().at(-1); badDoc.querySelector('.nx-citation').click();
  await until(() => badDoc.querySelector('.nx-chat-document')?.textContent.includes('HTTP 404'), 'document 404');
  check('원문 실패가 답변·출처를 제거하지 않음', badDoc.querySelector('.nx-chat-text').textContent.includes('롱스톤') && badDoc.querySelectorAll('.nx-chat-source').length === 2);

  const previousContextNote = $('nx-context-note').textContent;
  suggestionScenario = 'empty'; await select('P2');
  check('새 유저의 맥락 안내가 이전 유저 요청 개수를 물려받지 않음', $('nx-context-note').textContent !== previousContextNote && !/최근\s*\d+개\s*메시지/u.test($('nx-context-note').textContent));
  check('빈 추천 질문 상태', !$('nx-home-options').children.length && $('nx-suggestions-note').textContent.includes('아직 없어요'));
  suggestionScenario = 'error'; await select('P2');
  check('추천 조회 오류에도 자유 질문 가능', $('nx-suggestions-note').textContent.includes('계속할 수 있어요') && !$('nx-home-form').querySelector('[type="submit"]').disabled);
  await send('B 유저의 독립 질문');
  check('B 대화에 A 기록 혼입 없음', messages().length === 2 && !messages().some(n => n.textContent.includes('ERR400')));

  suggestionScenario = 'late';
  $('nx-change-user').click(); document.querySelector('#nx-users button[data-persona="P1"]').click();
  await pause(30); suggestionScenario = 'normal'; await select('P2'); await pause(300);
  check('이전 유저 지연 추천 응답 혼입 방지', $('nx-home-options').textContent.includes('novice') && !$('nx-home-options').textContent.includes('beginner'));
  await select('P1');
  const beforeDelay = askRequests().length;
  $('nx-home-input').value = 'DELAY A의 늦은 답변'; $('nx-home-form').requestSubmit();
  await until(() => askRequests().length > beforeDelay, 'delay request');
  $('nx-home-input').value = 'DELAY A의 늦은 답변'; $('nx-home-form').requestSubmit(); await pause(20);
  check('응답 대기 중 중복 전송 방지', askRequests().length === beforeDelay + 1);
  await select('P2'); await pause(350);
  check('이전 유저 지연 답변이 현재 화면에 표시되지 않음', messages().length === 2);
  await select('P1');
  check('지연 답변은 원래 A 대화에 저장', (await store.load('P1')).some(m => m.role === 'user' && m.content === 'DELAY A의 늦은 답변' && m.request_status === 'completed'));

  const scroll = $('nx-chat-scroll');
  scroll.dispatchEvent(new WheelEvent('wheel', { deltaY: -120, bubbles: true })); scroll.scrollTop = 24; scroll.dispatchEvent(new Event('scroll'));
  await pause(30); const oldTop = scroll.scrollTop; const oldPageTop = window.scrollY;
  await send('읽던 메시지 위치 유지 확인');
  check('이전 메시지 읽는 중 강제 자동 스크롤 없음', Math.abs(scroll.scrollTop - oldTop) <= 2, `${oldTop} → ${scroll.scrollTop}`);
  check('채팅 스크롤과 페이지 스크롤 독립', window.scrollY === oldPageTop);
  const overlay = $('nx-chat-overlay');
  check('채팅 전체 레이어가 투명', getComputedStyle(overlay).backgroundColor === 'rgba(0, 0, 0, 0)' && getComputedStyle(scroll).backgroundColor === 'rgba(0, 0, 0, 0)');
  const reopened = createConversationStore({ dbName });
  check('독립 IndexedDB 연결에서 대화 복원', (await reopened.load('P1')).length === (await store.load('P1')).length); await reopened.close();
  const aRows = await store.load('P1'), bRows = await store.load('P2'), cRows = await store.load('P3');
  check('A/B/C 로컬 저장 분리', aRows.every(m => m.persona_id === 'P1') && bRows.length === 2 && cRows.length === 26);
  check('요청에 persona·mate·level·system 필드 없음', askRequests().every(r => Object.keys(r.body).join() === 'messages' && r.body.messages.every(m => Object.keys(m).sort().join() === 'content,role')));

  const otherB = JSON.stringify(bRows), otherC = JSON.stringify(cRows);
  const sceneActor = $('nx-home-stage').firstElementChild;
  const background = document.querySelector('.nx-scene-bg').style.backgroundImage;
  const draft = '취소하면 그대로 남아야 하는 초안';
  $('nx-home-input').value = draft; $('nx-home-input').dispatchEvent(new Event('input', { bubbles: true }));
  const oldMessages = messages().map(node => node.dataset.messageId).join();
  const oldSources = document.querySelectorAll('.nx-chat-source').length;
  const clearsBeforeCancel = clearCalls.length;
  await requestReset(false); await pause(20);
  check('리셋 취소는 저장소·메시지·초안·출처를 바꾸지 않음', clearCalls.length === clearsBeforeCancel && JSON.stringify(await store.load('P1')) === JSON.stringify(aRows) && messages().map(node => node.dataset.messageId).join() === oldMessages && $('nx-home-input').value === draft && document.querySelectorAll('.nx-chat-source').length === oldSources);
  check('리셋 확인은 현재 유저를 명시', resetPrompts.at(-1).includes(getMateProfile('P1').name));

  const failurePending = await beginResetRequest('RESET-LATE 리셋 실패 후 정상 완료');
  const beforeFailure = JSON.stringify(await store.load('P1'));
  $('nx-home-input').value = draft;
  rejectReset = true; await requestReset();
  await until(() => !$('nx-reset-chat').disabled, 'failed reset completed');
  check('저장소 리셋 실패는 기존 기록·초안을 보존하고 오류 표시', JSON.stringify(await store.load('P1')) === beforeFailure && $('nx-home-input').value === draft && $('nx-home-note').textContent.length > 0);
  check('저장소 리셋 실패는 진행 중 요청을 취소하지 않음', !failurePending.aborted && !failurePending.signal.aborted);
  rejectReset = false; failurePending.resolve(lateAnswer());
  await until(() => $('nx-home-form').getAttribute('aria-busy') === 'false', 'pending request after reset failure');
  check('리셋 실패 뒤 진행 중 답변은 정상 보존', (await store.load('P1')).some(row => row.role === 'assistant' && row.content === '늦게 도착한 테스트 응답[1]'));

  await requestReset();
  await until(() => messages().length === 0 && !$('nx-reset-chat').disabled, 'accepted reset');
  check('확정 리셋은 현재 유저의 IndexedDB와 화면 대화만 삭제', (await store.load('P1')).length === 0 && messages().length === 0 && JSON.stringify(await store.load('P2')) === otherB && JSON.stringify(await store.load('P3')) === otherC);
  check('확정 리셋은 초안·출처·원문을 비우고 원래 인사를 복원', $('nx-home-input').value === '' && document.querySelectorAll('.nx-citation, .nx-chat-source, .nx-chat-document').length === 0 && greeting() === getMateProfile('P1').greeting);
  check('대화 리셋은 살아 있는 픽셀 그래픽을 교체하지 않음', $('nx-home-stage').firstElementChild === sceneActor && document.querySelector('.nx-scene-bg').style.backgroundImage === background);
  await select('P2'); await select('P1');
  check('리셋한 유저로 돌아와도 이전 초안과 대화가 복원되지 않음', $('nx-home-input').value === '' && messages().length === 0);
  await send('리셋 후 새 첫 질문');
  check('리셋 후 다음 요청은 새 질문 1개', askRequests().at(-1).body.messages.length === 1);

  for (const [question, expectedRequests, label] of [
    ['SAVE-PAUSE 첫 질문 저장 반환 대기', 0, '첫 질문 저장'],
    ['SAVEMANY-PAUSE 답변 저장 반환 대기', 1, '질문·답변 저장'],
    ['ERR500 FAILED-SAVE-PAUSE 실패 기록 저장 반환 대기', 1, '실패 기록 저장'],
  ]) {
    const requestCount = askRequests().length;
    $('nx-home-input').value = question; $('nx-home-form').requestSubmit();
    await until(() => pausedWrites.has(question), `${label} committed barrier`);
    check(`${label} 대기 조건은 실제 IndexedDB 커밋 이후`, (await store.load('P1')).some(row => row.role === 'user' && row.content === question));
    await requestReset();
    await until(() => messages().length === 0 && !$('nx-reset-chat').disabled, `${label} reset`);
    pausedWrites.get(question).release();
    await pause(60);
    check(`${label} 반환이 리셋 이후 기록·화면을 되살리지 않음`, (await store.load('P1')).length === 0 && messages().length === 0 && $('nx-home-note').textContent === '');
    check(`${label} 리셋 이후 추가 API 요청 없음`, askRequests().length === requestCount + expectedRequests);
  }

  for (const outcome of ['resolve', 'reject']) {
    const pending = await beginResetRequest(`RESET-LATE 성공 리셋 뒤 ${outcome}`);
    await requestReset();
    await until(() => pending.aborted && messages().length === 0 && !$('nx-reset-chat').disabled, `reset pending ${outcome}`);
    if (outcome === 'resolve') pending.resolve(lateAnswer()); else pending.reject(new Error('late fixture failure'));
    await pause(60);
    check(`리셋 이전 요청의 늦은 ${outcome}가 기록을 되살리지 않음`, messages().length === 0 && (await store.load('P1')).length === 0);
    check(`진행 중 리셋 ${outcome} 이후에도 다른 유저 기록 유지`, JSON.stringify(await store.load('P2')) === otherB && JSON.stringify(await store.load('P3')) === otherC);
    if (outcome === 'resolve') await send('두 번째 리셋의 새 첫 질문');
  }
  check('저장소 리셋은 선택된 persona에만 요청', clearCalls.every(id => id === 'P1'));
  sessionStorage.setItem(runKey, JSON.stringify({ phase: 'restore', resetRestore: true, dbName, expectedA: 0, otherB, otherC, report }));
  await store.close();
  location.reload();
}
run().catch(error => { report.push({ name: '브라우저 통합 실행', pass: false, detail: error.stack || error.message }); label.textContent = '통합 테스트 실패 · 결과 JSON 확인 · 테스트 픽스처'; publish('failed'); });
