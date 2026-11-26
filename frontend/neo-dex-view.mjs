/**
 * NEO-RETRO prototype view model. UI-independent and read-only.
 * Maps one client answer to what the Pokédex panel and scene show.
 * Facts come only from the answer and the local Red/Blue store; mates change
 * order, depth and wording of display, never the facts or calculations.
 */

/** Persona → mate pixel face. Personas and mates come from mate-content.mjs (MATE_PROFILES). */
export const GUIDES = Object.freeze([
  Object.freeze({ personaId: "P2", mate: "이슬이", mateId: "iseul" }),
  Object.freeze({ personaId: "P1", mate: "지우", mateId: "jiwoo" }),
  Object.freeze({ personaId: "P3", mate: "웅이", mateId: "woong" }),
]);
const FALLBACK = "P2";
export const guideOf = personaId => GUIDES.find(guide => guide.personaId === personaId) ?? GUIDES[0];

/** How each mate lays out the same facts: wording of factors, order and evidence depth. */
export const GUIDE_STYLE = Object.freeze({
  P1: Object.freeze({ factorDisplay: "words", showStab: false, showCombined: false, evidenceOpen: false, order: ["main", "conditions"] }),
  P2: Object.freeze({ factorDisplay: "both", showStab: false, showCombined: false, evidenceOpen: false, order: ["main", "conditions"] }),
  P3: Object.freeze({ factorDisplay: "numbers", showStab: true, showCombined: true, evidenceOpen: true, order: ["conditions", "main"] }),
});

export const STATUS_LABELS = Object.freeze({
  answered: "확인됨", partial: "일부만 확인", needs_context: "조건 필요", no_evidence: "근거 부족",
  unsupported: "지원 밖", unconnected: "연결 대기", error: "오류",
});

const STAT_LABELS = [["hp", "HP"], ["attack", "공격"], ["defense", "방어"], ["special", "특수"], ["speed", "스피드"]];

export function factorWord(factor) {
  if (factor == null || !Number.isFinite(factor)) return "계산 불가";
  if (factor === 0) return "효과 없음";
  if (factor < 1) return "덜 통함";
  if (factor === 1) return "보통";
  return factor >= 4 ? "아주 잘 통함" : "잘 통함";
}

/** Question intent from the answer the client returned (not from guessing the text). */
export function intentOf(result) {
  if (!result) return "idle";
  if (result.status === "error") return "error";
  if (result.comparison?.length) return "matchup";
  if (result.storyTopic === "taste") return "browse";
  if (["choice", "prepare", "strategy"].includes(result.storyTopic)) return "party";
  const title = String(result.title ?? "");
  if (title.includes("도감 조회")) return "pokemon";
  if (title.includes("기본 방어 상성")) return "defense";
  if (title === "Red/Blue 기술 수치" || title.includes("PP")) return "move";
  if (title.includes("습득")) return "learn";
  if (title === "상대 정보와 현재 공격부터") return "start";
  if (title === "Red/Blue 타입 관계 조회") return "typechart";
  return "notice";
}

/** "lead\n• a\n• b" → { lead, points } */
export function splitAnswer(text) {
  const lines = String(text ?? "").split("\n").map(line => line.trim()).filter(Boolean);
  const points = lines.filter(line => line.startsWith("•")).map(line => line.replace(/^•\s*/, ""));
  const lead = lines.filter(line => !line.startsWith("•")).join(" ");
  return { lead, points };
}

const typeChip = (store, key) => ({ key, ko: store.typesByName.get(key)?.name_ko ?? key });
const nameOf = (store, id) => store.pokemonById.get(id)?.name_ko ?? null;

function pokemonCard(store, id) {
  const row = store.pokemonById.get(id);
  if (!row) return null;
  return { id, name: row.name_ko, nameEn: row.name, number: String(id).padStart(3, "0"),
    types: row.types_gen1.map(key => typeChip(store, key)) };
}

function moveCard(store, id) {
  const row = store.movesById.get(id);
  const values = row?.values_by_version_group?.["red-blue"];
  if (!row || !values) return null;
  return { id, name: row.name_ko, type: typeChip(store, values.type), power: values.power ?? null,
    accuracy: values.accuracy ?? null, pp: values.pp ?? null };
}

function defenseGroups(store, pokemonId) {
  const target = store.pokemonById.get(pokemonId);
  if (!target) return [];
  const byFactor = new Map();
  for (const attack of store.types) {
    if (!store.typeChart[attack.name]) continue;
    const factor = target.types_gen1.reduce((value, type) => value * store.typeChart[attack.name][type], 1);
    if (factor === 1) continue;
    if (!byFactor.has(factor)) byFactor.set(factor, []);
    byFactor.get(factor).push(typeChip(store, attack.name));
  }
  return [...byFactor.entries()].sort((a, b) => b[0] - a[0]).map(([factor, types]) => ({ factor, word: factorWord(factor), types }));
}

const BATTLE_INTENTS = new Set(["matchup", "party", "start"]);

/** Battle conditions only where the answer depends on them; lookups show the version alone. */
function conditionsOf(result, store, intent) {
  const context = result?.context ?? {};
  const lines = [];
  lines.push(context.game === "red-blue" ? "Red/Blue 기준" : "게임 범위 확인 필요");
  if (!BATTLE_INTENTS.has(intent)) return lines;
  const opponent = nameOf(store, context.opponentId);
  if (context.mode === "example") lines.push(`예시 조건 S01 · 상대 ${opponent ?? "미정"} Lv.${context.conditions?.level ?? "?"}`);
  else if (context.mode === "example-variant") lines.push("S01-B 별도 가정 · 기본 S01은 그대로");
  else if (opponent) lines.push(`사용자 조건 · 상대 ${opponent}`);
  else lines.push("상대 미정");
  if (context.candidates?.length) {
    lines.push(`후보 · ${context.candidates.map(row => nameOf(store, row.id) ?? "미확인").join(" · ")}`);
  }
  lines.push("기본 타입 상성까지만 계산 · 실제 피해·승률은 계산하지 않음");
  return lines;
}

function mainSection(intent, result, store, personaId) {
  const context = result.context ?? {};
  if (intent === "matchup") {
    const opponent = pokemonCard(store, context.opponentId);
    const rows = result.comparison.map(row => {
      const move = moveCard(store, row.moveId);
      const selected = result.selection?.pokemonId === row.pokemonId && result.selection?.moveId === row.moveId;
      return { pokemonId: row.pokemonId, pokemonName: nameOf(store, row.pokemonId), moveId: row.moveId,
        moveName: move?.name ?? null, moveType: move?.type ?? null, typeFactor: row.typeFactor ?? null,
        stab: row.stab ?? null, combined: row.combined ?? null, state: row.state ?? null, reason: row.reason ?? null,
        word: factorWord(row.typeFactor), selected };
    });
    return { kind: "matchup", opponent, rows, basis: "기본 타입 상성" };
  }
  if (intent === "pokemon") {
    const card = pokemonCard(store, result.pokemonId);
    const stats = store.pokemonById.get(result.pokemonId)?.stats_gen1 ?? {};
    return card && { kind: "pokemon", ...card,
      stats: STAT_LABELS.filter(([key]) => Number.isFinite(stats[key])).map(([key, label]) => ({ key, label, value: stats[key] })) };
  }
  if (intent === "defense") {
    const card = pokemonCard(store, result.pokemonId);
    return card && { kind: "defense", ...card, groups: defenseGroups(store, result.pokemonId) };
  }
  if (intent === "move") {
    const moves = (result.entities ?? []).filter(row => row.kind === "move").map(row => moveCard(store, row.id)).filter(Boolean);
    return moves.length ? { kind: "moves", moves, ppOnly: String(result.title).includes("PP") } : null;
  }
  if (intent === "learn") {
    const moveId = (result.entities ?? []).find(row => row.kind === "move")?.id;
    return { kind: "learn", pokemon: pokemonCard(store, result.pokemonId), move: moveId ? moveCard(store, moveId) : null,
      lines: result.facts ?? [] };
  }
  if (intent === "start" || intent === "party") {
    return { kind: "party", opponent: pokemonCard(store, context.opponentId),
      candidates: (context.candidates ?? []).map(row => ({ ...pokemonCard(store, row.id),
        moves: row.moves.map(id => moveCard(store, id)).filter(Boolean) })).filter(row => row.id) };
  }
  if (intent === "browse") {
    const ids = (result.facts ?? []).map(fact => store.pokemon.find(row => fact.startsWith(`${row.name_ko} ·`))?.id).filter(Boolean);
    return { kind: "browse", pokemon: ids.map(id => pokemonCard(store, id)) };
  }
  return { kind: "notice", status: result.status, title: result.title, lines: (result.facts?.length ? result.facts : [result.answer]).filter(Boolean) };
}

function sceneOf(intent, result, section) {
  const context = result.context ?? {};
  if (intent === "matchup") {
    const pick = section.rows.find(row => row.selected) ?? section.rows[0];
    return { ally: pick?.pokemonId ?? null, opponent: context.opponentId ?? null, focus: null };
  }
  if (["pokemon", "defense", "learn"].includes(intent)) return { ally: null, opponent: null, focus: result.pokemonId ?? null };
  if (intent === "start" || intent === "party") {
    const known = (result.entities ?? []).find(row => row.kind === "pokemon" && row.id !== context.opponentId)?.id;
    return { ally: known ?? context.activePokemonId ?? null, opponent: context.opponentId ?? null, focus: null };
  }
  if (intent === "browse") return { ally: null, opponent: null, focus: section.pokemon[0]?.id ?? null };
  return null; // keep the previous scene
}

/**
 * @param {{result: object, text: string, personaId: string, store: object}} input
 */
export function buildDexView({ result, text, personaId = FALLBACK, store }) {
  const intent = intentOf(result);
  if (intent === "idle") return { intent, guide: guideOf(personaId) };
  const section = mainSection(intent, result, store, personaId) ?? { kind: "notice", status: result.status, title: result.title, lines: [result.answer].filter(Boolean) };
  const answer = splitAnswer(text);
  return {
    intent,
    status: result.status,
    statusLabel: STATUS_LABELS[result.status] ?? result.status,
    title: result.title,
    guide: guideOf(personaId),
    style: GUIDE_STYLE[personaId] ?? GUIDE_STYLE[FALLBACK],
    answer,
    section,
    scene: sceneOf(intent, result, section),
    entities: (result.entities ?? []).map(row => ({ kind: row.kind,
      id: row.id, name: row.kind === "pokemon" ? nameOf(store, row.id) : store.movesById.get(row.id)?.name_ko ?? null }))
      .filter(row => row.name),
    conditions: conditionsOf(result, store, intent),
    battleRelated: BATTLE_INTENTS.has(intent),
    sources: (result.sources ?? []).filter(source => source && source.label),
  };
}
