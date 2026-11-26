/** Original NEO-RETRO scenery, copied without changing geometry, assets or animation. */
const el = (tag, className, text) => { const node = document.createElement(tag); if (className) node.className = className; if (text != null) node.textContent = text; return node; };
const SPRITES = "assets/neo/sprites/";
let state = { manifest: {} };
const pokemonName = id => id === 25 ? "피카츄" : "";
export function setSpriteManifest(manifest) { state.manifest = manifest; }
/** Whole-pixel sprite whose feet sit on the wrapper's bottom edge. */
function sprite(id, { scale = 2, flip = false, focus = false, alt = "" } = {}) {
  const wrap = el("span", "nx-sprite-wrap" + (focus ? " is-focus" : ""));
  const img = el("img", "nx-sprite");
  img.src = `${SPRITES}${id}.png`; img.alt = alt; img.width = 64; img.height = 64; img.decoding = "async";
  const box = state.manifest[id]?.bbox ?? [0, 0, 64, 64];
  const cx = (box[0] + box[2]) / 2;
  wrap.style.setProperty("--s", scale);
  wrap.style.setProperty("--dx", `${(flip ? -1 : 1) * (32 - cx) * scale}px`);
  wrap.style.setProperty("--dy", `${(64 - box[3]) * scale}px`);
  if (flip) wrap.style.setProperty("--flip", -1);
  wrap.append(img);
  return wrap;
}

/* ---------- pixel scenery (static SVG, no motion) ---------- */
function rects(items, fill) { return items.map(([x, y, w, h]) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${fill}"/>`).join(""); }
function cloud(x, y) {
  return rects([[x + 6, y, 7, 1], [x + 3, y + 1, 13, 1], [x + 14, y + 1, 5, 1], [x + 2, y + 2, 19, 1], [x + 1, y + 3, 22, 1], [x, y + 4, 24, 1]], "#FBF7EE")
    + rects([[x + 1, y + 5, 22, 1]], "#D5E7F4");
}
export function sceneBackground() {
  const dither = (y, color) => Array.from({ length: 96 }, (_, i) => `<rect x="${i * 2 + (y % 2 ? 1 : 0)}" y="${y}" width="1" height="1" fill="${color}"/>`).join("");
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 192 108" shape-rendering="crispEdges" preserveAspectRatio="xMidYMax slice">
    <rect width="192" height="108" fill="#5F9FD2"/>
    <rect y="26" width="192" height="24" fill="#78B4DE"/>${dither(25, "#78B4DE")}${dither(24, "#78B4DE")}
    <rect y="50" width="192" height="14" fill="#96C6E8"/>${dither(49, "#96C6E8")}${dither(48, "#96C6E8")}
    <rect y="64" width="192" height="12" fill="#B8DAF1"/>${dither(63, "#B8DAF1")}
    ${cloud(14, 12)}${cloud(118, 6)}${cloud(138, 30)}${cloud(58, 40)}
    <rect y="72" width="192" height="6" fill="#9CBB76"/>${rects([[0, 70, 22, 2], [30, 71, 30, 1], [70, 69, 26, 3], [104, 71, 20, 1], [132, 70, 34, 2], [172, 71, 20, 1]], "#9CBB76")}
    <rect y="78" width="192" height="30" fill="#789D58"/>${rects([[0, 78, 192, 1]], "#6B904D")}
    ${rects([[8, 84, 3, 1], [9, 83, 1, 1], [40, 92, 3, 1], [41, 91, 1, 1], [76, 86, 3, 1], [77, 85, 1, 1], [120, 95, 3, 1], [121, 94, 1, 1], [150, 85, 3, 1], [151, 84, 1, 1], [176, 99, 3, 1], [177, 98, 1, 1], [24, 101, 3, 1], [25, 100, 1, 1], [100, 103, 3, 1], [101, 102, 1, 1]], "#587C3D")}
  </svg>`;
  return `url("data:image/svg+xml,${encodeURIComponent(svg)}")`;
}
export function platformImage() {
  const rows = [[14, 24], [8, 36], [4, 44], [2, 48], [2, 48], [4, 44], [8, 36], [14, 24]];
  const body = rows.map(([x, w], y) => `<rect x="${x}" y="${y + 1}" width="${w}" height="1" fill="${y < 3 ? "#9CBB76" : "#587C3D"}"/>`).join("");
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 52 10" shape-rendering="crispEdges"><rect x="14" y="0" width="24" height="1" fill="#4A6A33"/><rect x="14" y="9" width="24" height="1" fill="#3F5C2B"/>${body}</svg>`;
  return `url("data:image/svg+xml,${encodeURIComponent(svg)}")`;
}
export function actor(id, { left, bottom, scale, flip = false, focus = false, tag }) {
  const node = el("div", "nx-actor");
  node.style.left = left; node.style.bottom = bottom;
  node.append(sprite(id, { scale, flip, focus, alt: pokemonName(id) }));
  const platform = el("span", "nx-platform"); platform.style.setProperty("--s", scale);
  node.append(platform);
  if (tag) node.append(el("span", "nx-actor-tag", tag));
  return node;
}
