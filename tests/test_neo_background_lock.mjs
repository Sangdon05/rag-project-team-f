import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';

const frontend = name => new URL(`../frontend/${name}`, import.meta.url);
const hashText = bytes => createHash('sha256').update(bytes.toString('utf8').replaceAll('\r\n', '\n')).digest('hex');

test('the original stylesheet and live scenery stay fixed across platform line endings', async () => {
  const expected = {
    'neo.css': 'fc3807c32224d422e88a02a5581315ce20ec97bc3a2b2e0fc9c53450ca259432',
    'neo-scenery.mjs': '9634030869863ddd3d90b59fcec168ab56292bee2842ddc799dbef348fc680af',
  };
  for (const [name, hash] of Object.entries(expected)) {
    assert.equal(hashText(await readFile(frontend(name))), hash, name);
  }
  const css = await readFile(frontend('neo.css'), 'utf8');
  assert.match(css, /animation: nx-bob 1\.4s steps\(1\) infinite/);
});

test('the complete pixel assets and bundled font licenses are available', async () => {
  const sprites = await readdir(frontend('assets/neo/sprites/'));
  assert.equal(sprites.filter(name => name.endsWith('.png')).length, 151);
  for (let id = 1; id <= 151; id++) assert.ok(sprites.includes(`${id}.png`));
  const manifest = JSON.parse(await readFile(frontend('assets/neo/sprites/manifest.json'), 'utf8'));
  for (let id = 1; id <= 151; id++) assert.equal(manifest[id].bbox.length, 4);
  for (const path of ['mates/jiwoo-pixel.png', 'mates/iseul-pixel.png', 'mates/woong-pixel.png',
    'fonts/Galmuri11.woff2', 'fonts/Galmuri11-Bold.woff2', 'fonts/PretendardVariable.woff2',
    'fonts/OFL-Galmuri.md', 'fonts/LICENSE-Pretendard.txt']) {
    assert.ok((await readFile(frontend(`assets/neo/${path}`))).length > 0, path);
  }
});

test('HOME contains the greeting and transparent overlay without later journey routes', async () => {
  const html = await readFile(frontend('neo.html'), 'utf8');
  for (const id of ['nx-home-stage', 'nx-home-line', 'nx-chat-overlay']) assert.ok(html.includes(`id="${id}"`));
  assert.doesNotMatch(html, /id="(?:explore|prepare|nx-steps|nx-step-next)"|href="#(?:explore|prepare)"/);
  const css = await readFile(frontend('neo-chat.css'), 'utf8');
  assert.match(css, /\.nx-chat-overlay\s*\{[^}]*position: absolute;[^}]*background: transparent;/s);
  assert.doesNotMatch(css, /backdrop-filter\s*:|filter\s*:|\.nx-(?:scene|stage|sprite|actor)\s*\{/);
});
