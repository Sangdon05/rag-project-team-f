import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { normalizeEmbedding, embeddingPresentation, renderEmbeddingStatus } from '../frontend/neo-embedding.mjs';

const solar = { query_model: 'solar-embedding-2-query', document_model: 'solar-embedding-2-passage' };

function createHost() {
  class Node {
    constructor(tagName, document, value = '') {
      this.tagName = tagName; this.ownerDocument = document; this.value = value;
      this.children = []; this.attributes = new Map(); this.className = '';
    }
    get textContent() { return this.tagName === '#text' ? this.value : this.children.map(child => child.textContent).join(''); }
    set textContent(value) { this.replaceChildren(this.ownerDocument.createTextNode(String(value))); }
    set innerHTML(_) { throw new Error('HTML insertion is forbidden'); }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = children; }
    setAttribute(name, value) { this.attributes.set(name, String(value)); }
    getAttribute(name) { return this.attributes.get(name) ?? null; }
  }
  const document = {
    createTextNode(value) { return new Node('#text', this, value); },
    createElement(name) { return new Node(name, this); },
  };
  return document.createElement('p');
}
const all = node => [node, ...node.children.flatMap(all)];
const findClass = (node, name) => all(node).find(child => child.className.split(' ').includes(name));

test('embedding metadata is optional, copied, trimmed and restricted to the two model fields', () => {
  assert.equal(normalizeEmbedding(null), null);
  assert.equal(normalizeEmbedding(undefined), null);
  const original = { query_model: ' solar-embedding-2-query ', document_model: ' solar-embedding-2-passage ' };
  const result = normalizeEmbedding(original);
  assert.deepEqual(result, solar);
  assert.notEqual(result, original);
  assert.equal(original.query_model, ' solar-embedding-2-query ');
  assert.equal(normalizeEmbedding({ query_model: 'x'.repeat(200), document_model: 'y' }).query_model.length, 200);
  for (const value of [false, 'model', [], {}, { query_model: 'x' }, { ...solar, provider: 'extra' },
    { ...solar, query_model: '' }, { ...solar, query_model: '  ' }, { ...solar, document_model: 1 },
    { ...solar, query_model: 'x'.repeat(201) }, { ...solar, query_model: '\nmodel' },
    { ...solar, document_model: 'bad\u0000model' }, { ...solar, query_model: 'bad\u007fmodel' }]) {
    assert.throws(() => normalizeEmbedding(value), TypeError);
  }
});

test('raw model length and every Unicode Other category match the API boundary', () => {
  const paddedBoundary = ` ${'x'.repeat(198)} `;
  assert.equal(normalizeEmbedding({ ...solar, query_model: paddedBoundary }).query_model, 'x'.repeat(198));
  assert.equal(normalizeEmbedding({ ...solar, query_model: '😀'.repeat(200) }).query_model, '😀'.repeat(200));
  for (const model of [
    ` ${'x'.repeat(199)} `,
    'bad\u0085model',
    'bad\u202emodel',
    'bad\ud800model',
    'bad\ue000model',
    'bad\u0378model',
  ]) {
    assert.throws(() => normalizeEmbedding({ ...solar, query_model: model }), TypeError);
    assert.throws(() => normalizeEmbedding({ ...solar, document_model: model }), TypeError);
  }
});

test('the actual query model determines the color family without changing its displayed name', () => {
  for (const [model, family] of [
    ['solar-embedding-2-query', 'solar'], ['upstage/solar-embedding-2-query', 'solar'],
    ['text-embedding-3-small', 'openai'], ['openai/text-embedding-3-small', 'openai'],
    ['nlpai-lab/KURE-v1', 'kure'], ['KURE-v1', 'kure'],
    ['custom-embedding-v2', 'unknown'], ['gpt-6-luna', 'unknown'], ['not-kure-v1', 'unknown'],
  ]) {
    const presentation = embeddingPresentation({ query_model: model, document_model: 'document-model' });
    assert.equal(presentation.family, family, model);
    assert.equal(presentation.label, model);
    assert.equal(presentation.title, `질의 임베딩: ${model} · 문서 임베딩: document-model`);
  }
  assert.deepEqual(embeddingPresentation(undefined), { family: 'unknown', label: '임베딩 모델 정보 없음', title: '임베딩 모델 정보 없음' });
});

test('rag status has a decorative pulsing circle and independent fixed model text', () => {
  const host = createHost();
  renderEmbeddingStatus(host, { mode: 'rag', embedding: solar });
  const dot = findClass(host, 'nx-embedding-dot'), label = findClass(host, 'nx-embedding-label');
  assert.equal(dot.tagName, 'span');
  assert.equal(dot.getAttribute('aria-hidden'), 'true');
  assert.equal(dot.getAttribute('data-family'), 'solar');
  assert.ok(dot.className.includes('is-pulsing'));
  assert.equal(label.textContent, solar.query_model);
  assert.ok(!label.className.includes('is-pulsing'));
  assert.ok(!findClass(host, 'nx-embedding-status').className.includes('is-pulsing'));
  assert.ok(findClass(host, 'nx-embedding-status').getAttribute('title').includes(solar.document_model));
  assert.equal(host.textContent, `rag · ${solar.query_model}`);
  assert.equal(all(host).filter(node => node.tagName === 'button').length, 0);
});

test('old, malformed and unrecognized model metadata stays neutral and never claims a current environment', () => {
  for (const metadata of [undefined, null, { query_model: 'invalid' }, { query_model: 'custom-v2', document_model: 'custom-doc-v2' }]) {
    const host = createHost();
    renderEmbeddingStatus(host, { mode: 'rag', embedding: metadata });
    const dot = findClass(host, 'nx-embedding-dot');
    assert.equal(dot.getAttribute('data-family'), 'unknown');
    assert.ok(!dot.className.includes('is-pulsing'));
    assert.ok(!host.textContent.includes(solar.query_model));
  }
  const legacy = createHost(); renderEmbeddingStatus(legacy, { mode: 'rag' });
  assert.ok(legacy.textContent.includes('임베딩 모델 정보 없음'));
});

test('mock and llm answers never display an embedding dot or model, even with supplied metadata', () => {
  for (const mode of ['mock', 'llm']) {
    const host = createHost();
    renderEmbeddingStatus(host, { mode, embedding: solar });
    assert.equal(findClass(host, 'nx-embedding-dot'), undefined);
    assert.equal(findClass(host, 'nx-embedding-label'), undefined);
    assert.ok(!host.textContent.includes('embedding'));
    assert.ok(host.textContent.startsWith(mode));
  }
});

test('model names and tooltip text are inserted as literal text, never HTML', () => {
  const host = createHost();
  const hostile = '<img src=x onerror=alert(1)>';
  renderEmbeddingStatus(host, { mode: 'rag', embedding: { query_model: hostile, document_model: '<script>bad()</script>' } });
  assert.equal(findClass(host, 'nx-embedding-label').textContent, hostile);
  assert.equal(all(host).filter(node => ['img', 'script'].includes(node.tagName)).length, 0);
  assert.ok(findClass(host, 'nx-embedding-status').getAttribute('title').includes('<script>bad()</script>'));
});

test('only the circle receives the double heartbeat and both motion preferences disable it', async () => {
  const css = await readFile(new URL('../frontend/neo-chat.css', import.meta.url), 'utf8');
  assert.match(css, /\.nx-embedding-dot\.is-pulsing\s*\{\s*animation: nx-embedding-heartbeat/);
  assert.match(css, /@keyframes nx-embedding-heartbeat\s*\{[\s\S]*?10%, 25%\s*\{/);
  assert.match(css, /\.nx-embedding-label\s*\{[^}]*animation: none;[^}]*transform: none;/);
  assert.match(css, /body\[data-motion="off"\]\s+\.nx-embedding-dot\.is-pulsing\s*\{\s*animation: none;/);
  assert.match(css, /@media\s*\(prefers-reduced-motion: reduce\)\s*\{\s*\.nx-embedding-dot\.is-pulsing\s*\{\s*animation: none;/);
});
