/** Local browser preview: record lookup, nominal rules, and reviewed example intents.
 * This module never calls an LLM, a retriever, or a production question router.
 * Example matching is UI scaffolding; its answers are built from the loaded records.
 */
const DATA = "../data/processed/";
const SIMPLE_MOVES = new Set([52, 10, 55, 33, 84, 98]);
const STAT_NAMES = { hp: "HP", attack: "공격", defense: "방어", speed: "스피드", special: "특수" };
const copy = value => structuredClone(value);
const text = value => String(value ?? "").normalize("NFC").trim();
const key = value => text(value).toLowerCase().replace(/[\s_\-?!？!.。,，]/gu, "");
const escape = value => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const source = (label, file, detail) => ({ label, path: DATA + file, detail });
const calculationSource = () => ({ label: "로컬 규칙표 계산", path: "./flow-preview.mjs", detail: "공격→방어 타입 배율의 곱과 자속 계수. 실제 피해·명중·승률 계산 아님" });
const ask = (label, question) => ({ label, question, action: "ask" });
const pokemonSource = (id, detail) => source("정형 도감 조회", "pokemon.json", `id=${id}; ${detail}`);
const moveSource = (id, detail) => source("정형 기술 조회", "moves.json", `id=${id}; values_by_version_group[red-blue].${detail}`);

function indexRows(rows, label) {
  if (!Array.isArray(rows) || !rows.length) throw new TypeError(`${label}: nonempty array required`);
  const map = new Map();
  for (const row of rows) {
    if (!Number.isInteger(row.id) || map.has(row.id)) throw new TypeError(`${label}: invalid or duplicate id`);
    map.set(row.id, row);
  }
  return map;
}

export function buildStore({ pokemon, moves, types, typeChart, scenarios, damageClassification, generatedQuestions } = {}) {
  const pokemonById = indexRows(pokemon, "pokemon");
  const movesById = indexRows(moves, "moves");
  const typesById = indexRows(types, "types");
  const typesByName = new Map(types.map(row => [row.name, row]));
  if (!typeChart || typeof typeChart !== "object") throw new TypeError("typeChart required");
  for (const attacking of types) for (const defending of types) {
    if (![0, 0.5, 1, 2].includes(typeChart[attacking.name]?.[defending.name])) throw new TypeError("Incomplete type chart");
  }
  const moveByName = new Map(moves.map(row => [row.name, row]));
  const classifications = new Map((damageClassification?.moves ?? []).map(row => [row.id, row]));
  const aliases = [];
  for (const [kind, rows] of [["pokemon", pokemon], ["move", moves]]) for (const row of rows) {
    for (const alias of new Set([row.name_ko, row.name].filter(Boolean))) aliases.push({ kind, row, alias });
  }
  const cases = Array.isArray(scenarios?.cases) ? scenarios.cases : [];
  const caseQuestions = new Map();
  for (const row of cases) for (const question of [row.question, row.prompt].filter(Boolean)) caseQuestions.set(key(question), row.id);
  for (const row of (Array.isArray(generatedQuestions) ? generatedQuestions : generatedQuestions?.candidates ?? generatedQuestions?.questions ?? [])) {
    if (row.question && (row.seed_id || row.id)) caseQuestions.set(key(row.question), row.seed_id || row.id);
  }
  return { pokemon, moves, types, typeChart, scenarios, generatedQuestions, cases, caseQuestions, aliases,
    pokemonById, movesById, moveByName, typesById, typesByName, classifications };
}

/** Longest names win over substrings (뮤츠/뮤, 쥬피썬더/썬더). */
export function detectEntities(query, store) {
  const q = text(query);
  const matches = [];
  for (const { kind, row, alias } of store.aliases) {
    const pattern = escape(alias).replace(/[-_ ]+/g, "[-_\\s]*");
    const regex = new RegExp(pattern, "giu");
    for (const match of q.matchAll(regex)) {
      if (/[a-z]/i.test(alias) && (/[a-z]/i.test(q[match.index - 1] ?? "") || /[a-z]/i.test(q[match.index + match[0].length] ?? ""))) continue;
      matches.push({ index: match.index, end: match.index + match[0].length, kind, row });
    }
  }
  const numberPattern = /#\s*(\d{1,3})|(?:도감|포켓몬)\s*(\d{1,3})\s*(?:번)?|(\d{1,3})\s*번|(?:기술)\s*(\d{1,3})\s*(?:번)?/gu;
  for (const match of q.matchAll(numberPattern)) {
    if (!match[4] && /(?:타입|type)\s*(?:id\s*)?$/i.test(q.slice(0, match.index))) continue;
    const kind = match[4] ? "move" : "pokemon";
    const row = (kind === "move" ? store.movesById : store.pokemonById).get(Number(match[4] || match[1] || match[2] || match[3]));
    if (row) matches.push({ index: match.index, end: match.index + match[0].length, kind, row });
  }
  if (/^\d{1,3}$/.test(q) && store.pokemonById.has(Number(q))) matches.push({ index: 0, end: q.length, kind: "pokemon", row: store.pokemonById.get(Number(q)) });
  matches.sort((a, b) => a.index - b.index || (b.end - b.index) - (a.end - a.index));
  const occupied = [], seen = new Set(), entities = [];
  for (const match of matches) {
    if (occupied.some(span => match.index < span.end && match.end > span.index)) continue;
    occupied.push(match);
    const identity = `${match.kind}:${match.row.id}`;
    if (seen.has(identity)) continue;
    seen.add(identity);
    const entity = { id: match.row.id, name: match.row.name_ko || match.row.name, kind: match.kind };
    if (match.kind === "move") entity.type = match.row.values_by_version_group?.["red-blue"]?.type;
    entities.push(entity);
  }
  return entities;
}

export function initialContext() {
  return { game: "red-blue", mode: "example", opponentId: 95,
    candidates: [{ id: 4, moves: [52, 10] }, { id: 7, moves: [55, 33] }, { id: 25, moves: [84, 98] }],
    comparisonBasis: "basic_type", activePokemonId: 25, selection: null,
    conditions: { level: 20, ppEnough: true, statusChanges: false, baseTypes: true } };
}

function contextCopy(context) {
  if (context == null) return initialContext();
  const result = { game: "red-blue", mode: "custom", opponentId: null, candidates: [], comparisonBasis: null, selection: null, ...copy(context) };
  result.candidates = Array.isArray(result.candidates) ? result.candidates.map(row => ({ ...row, moves: Array.isArray(row.moves) ? [...row.moves] : [] })) : [];
  return result;
}

function baseResult(context, entities) {
  return { status: "unconnected", title: "도감 자료 연결 필요", answer: "이 질문은 로컬 체험에서 연결하지 않았어요. 실제 RAG 검색은 아직 연결되지 않았어요.",
    facts: [], sources: [], pokemonId: entities.find(row => row.kind === "pokemon")?.id ?? context.activePokemonId ?? null,
    entities, followups: [ask("포켓몬 정보", "피카츄 정보 알려줘")], context };
}

function typesLabel(pokemon, store) {
  return pokemon.types_gen1.map(name => store.typesByName.get(name)?.name_ko || name).join(" · ");
}

function nominal(pokemonId, moveId, opponentId, store) {
  const pokemon = store.pokemonById.get(pokemonId), move = store.movesById.get(moveId), target = store.pokemonById.get(opponentId);
  const values = move?.values_by_version_group?.["red-blue"];
  const classification = store.classifications.get(moveId)?.classification ?? (SIMPLE_MOVES.has(moveId) ? "regular_damage" : "unknown");
  const row = { pokemonId, moveId, typeFactor: null, stab: null, combined: null, classification };
  if (!pokemon || !target || !values) return { ...row, state: "unsupported", reason: "조회할 개체·Red/Blue 기술 값 부족" };
  if (classification !== "regular_damage") return { ...row, state: classification === "status" ? "not_applicable" : "unsupported", reason: classification === "status" ? "변화 기술의 직접 피해 배율은 이 계산 대상이 아님" : "특수 방식·미확인 기술의 계산은 지원 밖" };
  const typeFactor = target.types_gen1.reduce((factor, type) => factor * store.typeChart[values.type][type], 1);
  const stab = pokemon.types_gen1.includes(values.type) ? 1.5 : 1;
  return { ...row, state: "supported", typeFactor, stab, combined: typeFactor * stab };
}

function pokemonFacts(result, pokemon, query, store) {
  const stats = pokemon.stats_gen1 || {};
  result.status = "answered";
  result.title = `${pokemon.name_ko} 도감 조회`;
  result.pokemonId = pokemon.id;
  result.context.activePokemonId = pokemon.id;
  result.facts = [`도감 번호 ${pokemon.id} · ${pokemon.name_ko} (${pokemon.name})`, `Red/Blue 타입: ${typesLabel(pokemon, store)}`];
  const requested = Object.keys(STAT_NAMES).filter(name => new RegExp(`${STAT_NAMES[name]}|${name}`, "i").test(query));
  const fields = requested.length ? requested : /종족치|스탯|능력치|stats/i.test(query) ? Object.keys(STAT_NAMES) : [];
  for (const name of fields) if (stats[name] != null) result.facts.push(`${STAT_NAMES[name]} 종족치: ${stats[name]}`);
  result.answer = result.facts.join(". ") + ". 정형 도감 레코드를 조회한 결과예요.";
  result.sources = [pokemonSource(pokemon.id, "name/name_ko/types_gen1/stats_gen1")];
  result.followups = [ask("현재 기술 비교", "지금 가진 포켓몬과 기술을 비교해줘"), ask("기술 습득", `${pokemon.name_ko}는 어떤 기술을 배워?`)];
  return result;
}

function learnsetAnswer(result, pokemon, move, store) {
  if (!pokemon) return { ...result, status: "needs_context", title: "배울 포켓몬 확인", answer: "어떤 포켓몬이 배우는 기술인지 알려줘요. 지금 기술을 보유한 것으로 바꾸지는 않았어요." };
  const rows = pokemon.learnset.filter(row => row.version_group === "red-blue" && (!move || row.move === move.name));
  result.pokemonId = pokemon.id;
  result.status = rows.length ? "answered" : "partial";
  result.title = `${pokemon.name_ko}의 Red/Blue 습득 기록`;
  result.facts = rows.map(row => {
    const name = store.moveByName.get(row.move)?.name_ko || row.move;
    return `${name}: ${row.method === "machine" ? "기술머신·비전머신 방법 기록 (level=0은 레벨업 습득 아님)" : row.method === "level-up" ? `레벨업 ${row.level}` : row.method}`;
  });
  if (move && rows.length && !rows.some(row => row.method === "level-up")) result.facts.push("해당 Red/Blue 습득표에 레벨업 기록은 없음");
  result.answer = rows.length ? `${result.facts.join(". ")}. 배울 수 있다는 기록이며 현재 보유·머신 소유를 확인한 것은 아니에요.` : "해당 버전의 습득 기록을 확인하지 못했어요. 빈 결과만으로 모든 획득 경로가 불가능하다고 단정하지 않아요.";
  result.sources = [pokemonSource(pokemon.id, `learnset[version_group=red-blue${move ? `,move=${move.name}` : ""}]`)];
  result.followups = [ask("현재 기술로 비교", "지금 가진 기술로 다시 비교해줘")];
  return result;
}

function moveFacts(result, moves) {
  if (moves.length === 1) result.context.lastMoveId = moves[0].id;
  result.status = "answered";
  result.title = "Red/Blue 기술 수치";
  result.facts = moves.map(move => {
    const values = move.values_by_version_group?.["red-blue"];
    return values ? `${move.name_ko}: 타입 ${values.type}, 위력 ${values.power ?? "값 없음"}, 기본 명중률 ${values.accuracy ?? "값 없음"}, 기본 PP ${values.pp ?? "값 없음"}` : `${move.name_ko}: Red/Blue 값 없음`;
  });
  result.answer = `${result.facts.join(". ")}. 위력은 실제 피해량이 아니며 명중률 100도 항상 명중을 뜻하지 않아요.`;
  result.sources = moves.map(move => moveSource(move.id, "type/power/accuracy/pp"));
  result.followups = [ask("현재 기술 비교", "지금 가진 기술의 기본 상성을 비교해줘")];
  return result;
}

function comparisonAnswer(result, query, pokemonEntities, moveEntities, store, forceAll = false) {
  const context = result.context;
  if (context.conditions?.ppEnough === false) return { ...result, status: "needs_context", title: "현재 사용 가능한 기술 확인", answer: "현재 PP 조건이 달라졌어요. 기술 보유 목록은 유지하고, 지금 사용할 수 있는 기술을 확인한 뒤 비교해줘요. 기본 PP를 현재 잔량으로 자동 지정하지 않아요.", followups: [] };
  let opponentId = context.opponentId;
  for (const entity of pokemonEntities) {
    const pokemon = store.pokemonById.get(entity.id);
    const names = [pokemon.name_ko, pokemon.name].filter(Boolean).map(escape).join("|");
    if (new RegExp(`(?:${names})\\s*(?:한테|에게|상대로)|상대(?:는|가)?\\s*(?:${names})`, "i").test(query)) opponentId = entity.id;
  }
  if (!store.pokemonById.has(opponentId) || !context.candidates.length || context.candidates.some(row => !row.moves.length)) {
    return { ...result, status: "needs_context", title: "비교할 조건 확인", answer: "상대 포켓몬, 내 후보, 각 후보가 현재 가진 기술을 확인해줘요. 도감의 습득표를 현재 기술로 자동 채우지 않아요.", followups: [] };
  }
  if (!context.comparisonBasis && !/타입|상성|배율|자속/.test(query)) return { ...result, status: "needs_context", title: "비교 기준 확인", answer: "‘쎄?’가 기본 위력, 타입 상성, 실제 피해 중 무엇을 뜻하는지 확인해줘요. 실제 피해 계산은 연결되지 않았어요.", followups: [ask("기본 상성으로 비교", "현재 기술을 기본 타입 상성으로 비교해줘")] };
  if (/타입|상성|배율|자속/.test(query)) context.comparisonBasis = "basic_type";
  if (opponentId !== context.opponentId) { context.opponentId = opponentId; context.selection = null; result.clearSelection = true; }
  const namedMoves = new Set(moveEntities.map(row => row.id));
  const namedCandidates = new Set(pokemonEntities.map(row => row.id).filter(id => id !== opponentId));
  const candidates = forceAll || !namedCandidates.size ? context.candidates : context.candidates.filter(row => namedCandidates.has(row.id));
  const comparison = candidates.flatMap(candidate => candidate.moves
    .filter(id => forceAll || !namedMoves.size || namedMoves.has(id))
    .map(id => nominal(candidate.id, id, opponentId, store)));
  if (!comparison.length || (!forceAll && [...namedMoves].some(id => !comparison.some(row => row.moveId === id)))) return { ...result, status: "needs_context", title: "현재 기술 확인", answer: "질문에 나온 기술이 입력한 후보의 현재 기술 목록에 있는지 확인해줘요. 배울 수 있는 기술을 현재 기술로 추가하지 않았어요.", followups: [] };
  const supported = comparison.filter(row => row.state === "supported");
  result.comparison = comparison;
  result.status = supported.length === comparison.length ? "answered" : supported.length ? "partial" : "unsupported";
  result.title = "현재 기술의 기본 상성 비교";
  result.facts = comparison.map(row => {
    const name = `${store.pokemonById.get(row.pokemonId)?.name_ko} · ${store.movesById.get(row.moveId)?.name_ko}`;
    return row.typeFactor == null ? `${name}: ${row.reason}` : `${name}: 기본 타입 배율 ${row.typeFactor}, 자속 ${row.stab}, 명목 결합계수 ${row.combined}`;
  });
  if (/위력|명중|얼마나\s*(?:쎄|쎈|센|세)|잘\s*맞/.test(query) || store.caseQuestions.get(key(query)) === "P1-02") {
    for (const moveId of new Set(comparison.map(row => row.moveId))) {
      const move = store.movesById.get(moveId), values = move.values_by_version_group["red-blue"];
      result.facts.push(`${move.name_ko}: 기본 위력 ${values.power ?? "값 없음"}, 기본 명중률 ${values.accuracy ?? "값 없음"}, 기본 PP ${values.pp ?? "값 없음"}`);
    }
  }
  result.sources = [pokemonSource(opponentId, "types_gen1"), source("정형 타입 관계 조회", "type_chart.json", "공격 기술 타입 → 상대의 각 방어 타입 배율을 곱함"), calculationSource()];
  if (store.classifications.size) result.sources.push(source("정형 피해 방식 분류", "red_blue_move_damage_classification.json", "일반 피해만 계산, 변화/특수 방식/미확인 기술의 배율은 null"));
  for (const row of comparison) result.sources.push(moveSource(row.moveId, "type"));
  if (store.classifications.size) result.sources.push(source("직접 피해 방식 분류", "red_blue_move_damage_classification.json", "일반 피해만 명목 계수를 계산; 변화·특수 방식·미확인과 구별"));
  const bestFactor = supported.length ? Math.max(...supported.map(row => row.typeFactor)) : null;
  const best = supported.filter(row => row.typeFactor === bestFactor);
  const choosing = forceAll || /비교|추천|누구|어떤|골라|준비|쎄|뭐.*(?:써|세)|유리|쓸까|통해/.test(query);
  result.answer = "입력한 현재 기술의 기본 타입 배율을 비교했어요. 자속을 포함한 명목 계수와 실제 피해량은 다르며 승리나 승률을 계산한 결과가 아니에요.";
  if (!supported.length) result.answer = "이 기술들의 피해 방식은 현재 일반 피해 계산 범위에 들어가지 않아요. 지원 밖(null)을 타입 무효(0배)로 해석하지 않아요.";
  if (!supported.length) result.answer = "이 기술의 직접 피해 방식은 기본 계수 계산의 지원 대상이 아니에요. 계산하지 못한 값(null)과 무효 배율(0)을 구분해요.";
  result.followups = [ask("상대 정보", `${store.pokemonById.get(opponentId).name_ko} 정보 알려줘`)];
  if (choosing && best.length === 1 && bestFactor > 0 && supported.length === comparison.length) {
    const row = best[0];
    result.selection = { pokemonId: row.pokemonId, moveId: row.moveId, reason: "입력한 현재 기술 중 기본 타입 배율을 기준으로 한 조건부 선택" };
    result.pokemonId = row.pokemonId;
    result.answer = `기본 공격 상성만 보면 ${store.pokemonById.get(row.pokemonId).name_ko}의 ${store.movesById.get(row.moveId).name_ko}를 우선 고려할 수 있어요. 승리를 보장하지 않으며 실제 피해량·승률은 계산하지 않았어요.`;
    result.followups.unshift({ label: "이 선택 준비", question: "이 선택을 준비할게", action: "prepare", selection: { ...result.selection } });
    result.followups.push(ask("기술 수치 보기", `${store.movesById.get(row.moveId).name_ko} 위력 명중률 PP 알려줘`));
  } else if (choosing && best.length > 1) result.answer += " 같은 기본 배율의 기술이 여럿이므로 이 기준만으로 유일한 최고 후보를 정하지 않아요. 같은 배율이 실제 피해 동률을 뜻하지도 않아요.";
  return result;
}

function typeOnlyAnswer(result, query, store) {
  const idMatch = query.match(/(?:타입|type)\s*(?:id\s*)?#?\s*(\d{1,2})/i);
  const mentions = store.types.flatMap(type => {
    const match = query.match(new RegExp(`${escape(type.name_ko)}\\s*타입|\\b${escape(type.name)}\\b`, "iu"));
    return match ? [{ type, index: match.index, end: match.index + match[0].length }] : [];
  }).sort((a, b) => a.index - b.index);
  if (idMatch && store.typesById.has(Number(idMatch[1]))) mentions.splice(0, mentions.length, { type: store.typesById.get(Number(idMatch[1])), index: 0, end: query.length });
  if (!mentions.length) return null;
  result.status = "answered"; result.title = "Red/Blue 타입 관계 조회";
  if (mentions.length > 1) {
    const attack = mentions.find(row => /^\s*(?:의\s*)?(?:공격|기술)/.test(query.slice(row.end))) ?? mentions[0];
    const defense = mentions.find(row => /^\s*(?:의\s*)?방어/.test(query.slice(row.end))) ?? mentions.find(row => row !== attack);
    result.facts = [`${attack.type.name_ko} 공격 → ${defense.type.name_ko} 방어: ${store.typeChart[attack.type.name][defense.type.name]}배`];
    result.answer = result.facts[0] + ". 공격·방어가 별도로 표시되지 않으면 입력의 첫 타입을 공격, 다음 타입을 방어로 읽어요.";
    result.sources = [source("정형 타입 관계 조회", "type_chart.json", "공격 타입 → 방어 타입")];
  } else if (/상성|약점|저항|공격|방어|통해/.test(query)) {
    const selected = mentions[0].type, incoming = /약점|저항|방어/.test(query);
    result.facts = store.types.flatMap(other => {
      const factor = incoming ? store.typeChart[other.name][selected.name] : store.typeChart[selected.name][other.name];
      return factor === 1 ? [] : [`${incoming ? other.name_ko : selected.name_ko} 공격 → ${incoming ? selected.name_ko : other.name_ko} 방어: ${factor}배`];
    });
    result.answer = `${selected.name_ko}의 기본 ${incoming ? "방어" : "공격"} 타입 관계예요. 실제 피해량은 계산하지 않아요.`;
    result.sources = [source("정형 타입 관계 조회", "type_chart.json", incoming ? "입력 타입을 방어로 계산" : "입력 타입을 공격으로 계산")];
  } else {
    const selected = mentions[0].type;
    result.facts = [`${selected.name_ko} (${selected.name}) · 타입 ID ${selected.id}`]; result.answer = result.facts[0];
    result.sources = [source("정형 타입 목록", "types.json", `id=${selected.id}`)];
  }
  return result;
}

export function answerPreview(question, suppliedContext, store) {
  const query = text(question), context = contextCopy(suppliedContext);
  const entities = detectEntities(query, store);
  const pokemonEntities = entities.filter(row => row.kind === "pokemon"), moveEntities = entities.filter(row => row.kind === "move");
  const pokemon = store.pokemonById.get(pokemonEntities[0]?.id), moves = moveEntities.map(row => store.movesById.get(row.id));
  const caseId = store.caseQuestions.get(key(query));
  const result = baseResult(context, entities);
  if (!query) return { ...result, status: "needs_context", title: "질문 입력", answer: "궁금한 포켓몬이나 기술을 입력해줘요.", followups: [] };
  if (context.game !== "red-blue") return { ...result, status: "unsupported", title: "게임 범위 확인", answer: "이 로컬 체험의 수치와 규칙은 영문 Red/Blue 기준이에요. 다른 게임으로 자동 대체하지 않아요.", followups: [] };
  const unknownOpponent = /상대(?:\s*포켓몬)?(?:는|가|를|도)?\s*(?:(?:아직|지금은|현재는|잘)\s*)*(?:몰라|모르|모름|미정|불명|안\s*정|정해지지|확인\s*(?:못|안))|상대(?:는|가)?\s*(?:아직\s*)?누(?:구|군지)[^.!?\n]*(?:몰라|모르|모름)/.test(query);
  if (unknownOpponent) {
    context.opponentId = null; context.selection = null; result.clearSelection = true;
  } else {
    for (const entity of pokemonEntities) {
      const record = store.pokemonById.get(entity.id);
      const names = [record.name_ko, record.name].filter(Boolean).map(escape).join("|");
      if (new RegExp(`상대(?:\\s*포켓몬)?(?:는|가|:)?\\s*(?:${names})`, "i").test(query) && context.opponentId !== entity.id) {
        context.opponentId = entity.id; context.selection = null; result.clearSelection = true;
      }
    }
  }
  const excludesPokemon = pokemonEntities.some(entity => {
    const record = store.pokemonById.get(entity.id);
    const names = [record.name_ko, record.name].filter(Boolean).map(escape).join("|");
    return new RegExp(`(?:${names})(?:\\s*(?:은|는|을|를|이|가))?\\s*(?:말고|제외|빼(?:고|면|줘|자|도))`, "i").test(query);
  });
  if (excludesPokemon) {
    context.selection = null;
    return { ...result, status: "needs_context", title: "후보 제외 조건 확인", clearSelection: true,
      answer: "후보를 제외하는 조건은 이 체험에서 자동 적용하지 않았어요. 조건 확인·수정에서 비교할 후보와 현재 기술을 확인해줘요.", followups: [] };
  }
  if (/실제\s*피해|피해량|승률|확정\s*타수|몇\s*방|몇\s*턴|\bKO\b|이길\s*확률/i.test(query) || caseId === "P3-03") return { ...result, status: "unsupported", title: "실제 대전 계산은 지원 밖", answer: "현재 체험은 기본 타입 배율과 자속의 명목 계수만 계산해요. 실제 피해량·확정 타수·승률은 산출하지 않아요. 지원 밖이라는 뜻이 기술 무효(배율 0)라는 뜻은 아니에요.", sources: [calculationSource()], followups: [ask("기본 계수 확인", "꼬부기 물대포의 롱스톤 상대 타입 배율과 자속을 분리해줘")] };
  if (!pokemonEntities.length && !moveEntities.length) {
    const typeAnswer = typeOnlyAnswer(result, query, store);
    if (typeAnswer) return typeAnswer;
  }
  const absent = /없|미보유|제외|빼/.test(query) && moveEntities.length;
  const hypothetical = /가정|만약|없(?:으면|다면|어도)|없는\s*셈|없을\s*경우|없는\s*거야|없(?:어|나|지)\s*\?/.test(query);
  const learning = /배워|배우|습득|레벨\s*(?:업|올|더)|레벨.*생겨|기술머신|learn/i.test(query);
  if (absent && hypothetical) {
    const followups = moves.flatMap(move => {
      const owners = context.candidates.filter(row => row.moves.includes(move.id) && (!pokemonEntities.length || pokemonEntities.some(entity => entity.id === row.id)));
      if (owners.length !== 1) return [];
      const owner = store.pokemonById.get(owners[0].id);
      return owner ? [ask(`실제 미보유 확인 · ${move.name_ko}`, `${owner.name_ko} ${move.name_ko}는 지금 없어. 남은 기술로 다시 비교해줘`)] : [];
    });
    return { ...result, status: "needs_context", title: "가정과 현재 기술 구분", answer: "가정만으로 현재 기술이나 선택을 바꾸지 않았어요. 실제로 없는 기술인지 확인한 뒤 현재 목록을 바꿔줘요.", followups };
  }
  let changed = false;
  if (absent && !/PP|피피|남은\s*(?:횟수|사용)|잔량|모르|있을까|없어\s*\?/i.test(query)) {
    for (const move of moves) {
      const owners = context.candidates.filter(row => row.moves.includes(move.id) && (!pokemonEntities.length || pokemonEntities.some(entity => entity.id === row.id)));
      if (owners.length === 1) { owners[0].moves = owners[0].moves.filter(id => id !== move.id); changed = true; }
    }
    if (changed) { context.selection = null; result.clearSelection = true; }
  }
  const ppRequested = /PP|피피|몇\s*번|몇\s*회/i.test(query) || caseId === "P2-02";
  const otherStats = /위력|명중|얼마나\s*(?:쎄|쎈|센|세)|잘\s*맞/.test(query);
  const ppConcept = /뜻|뭐|계속|무한|못|남은|잔량|몇\s*(?:번|회)/.test(query) || caseId === "P2-02";
  if (ppRequested && (!otherStats || ppConcept)) {
    const move = moves[0] || store.movesById.get(context.lastMoveId);
    if (!move) return { ...result, status: "needs_context", title: "기술 확인", answer: "어떤 기술의 PP를 확인할지 알려줘요.", followups: [] };
    const pp = move.values_by_version_group?.["red-blue"]?.pp;
    context.lastMoveId = move.id;
    const zeroEntered = !hypothetical && /(?:PP|피피)\s*(?:가|는|은|:)?\s*0(?:\D|$)/i.test(query);
    if (zeroEntered) { context.conditions = { ...context.conditions, ppEnough: false }; context.selection = null; result.clearSelection = true; }
    const numericOnly = !ppConcept;
    const statsFacts = otherStats ? moveFacts(baseResult(context, entities), moves).facts : [];
    return { ...result, status: numericOnly && !zeroEntered ? "answered" : "partial", title: numericOnly && !zeroEntered ? "기본 PP 조회" : "PP는 확인 가능한 부분만 안내", answer: `${move.name_ko}의 Red/Blue 기본 PP는 ${pp ?? "값 없음"}예요. 현재 남은 PP와 같은 값으로 단정하지 않아요.${numericOnly && !zeroEntered ? "" : " PP의 뜻·사용 제한을 설명하는 검수 원문은 아직 연결하지 못했어요."}`, facts: [...statsFacts, `기본 PP: ${pp ?? "값 없음"}`, zeroEntered ? "사용자 입력 현재 PP: 0 · 기술 보유 목록은 유지" : "현재 남은 PP: 별도 입력·검증 필요"], sources: [moveSource(move.id, "pp")], followups: [ask("기술 수치", `${move.name_ko} 위력과 명중률 알려줘`)] };
  }
  if (learning) return learnsetAnswer(result, pokemon || (moves.length ? store.pokemonById.get(context.candidates.find(row => row.moves.includes(moves[0].id))?.id) : null), moves[0], store);
  if (changed || caseId === "P3-02") return comparisonAnswer(result, query, [], [], store, true);
  if (/뭐부터|뭘\s*먼저|먼저\s*뭘|어디부터|뭐.*먼저|시작점/.test(query) || caseId === "P2-01") {
    const target = store.pokemonById.get(context.opponentId);
    result.status = target ? "answered" : "needs_context";
    result.title = "상대 정보와 현재 공격부터";
    result.answer = target ? `먼저 상대 정보와 지금 쓸 수 있는 공격을 함께 보면 돼요. ${target.name_ko}는 도감 ${target.id}번, ${typesLabel(target, store)} 타입이에요. 이름을 안다는 말과 보유 목록은 구분하고 입력한 후보·기술을 유지했어요.` : "기본 도감 정보부터 볼 수 있어요. 상대에 맞춰 비교하려면 상대·내 후보·현재 기술을 알려줘요.";
    result.facts = target ? [`${target.name_ko}: ${target.id}번 · ${typesLabel(target, store)}`, "안내 순서는 로컬 화면 설계이며 유일 정답이 아님"] : [];
    result.sources = target ? [pokemonSource(target.id, "id/name_ko/types_gen1")] : [];
    result.pokemonId = target?.id ?? pokemon?.id ?? null;
    result.followups = [ask("현재 공격 비교", "세 마리의 현재 기술로 누구를 준비할지 비교해줘"), ask("피카츄 정보", "피카츄 정보 알려줘")];
    return result;
  }
  if (pokemon && /약점|저항|방어\s*상성/.test(query)) {
    const factors = store.types.map(type => ({ type, factor: pokemon.types_gen1.reduce((value, defense) => value * store.typeChart[type.name][defense], 1) }));
    result.status = "answered"; result.title = `${pokemon.name_ko}의 기본 방어 상성`; result.pokemonId = pokemon.id;
    result.facts = factors.filter(row => row.factor !== 1).map(row => `${row.type.name_ko} 공격: 기본 타입 배율 ${row.factor}`);
    result.answer = "공격 기술의 타입을 기준으로 계산한 기본 방어 상성이에요. 실제 피해·생존 여부는 계산하지 않았어요.";
    result.sources = [pokemonSource(pokemon.id, "types_gen1"), source("정형 타입 관계 계산", "type_chart.json", "각 방어 타입 관계의 곱")];
    return result;
  }
  if (/비교|추천|누구|준비|쎄|유리|통해|통하|써도|뭐\s*써|어떤\s*공격|배율|자속|기본\s*상성/.test(query) || ["P1-01", "P1-02", "P2-03", "P3-01"].includes(caseId)) return comparisonAnswer(result, query, pokemonEntities, moveEntities, store);
  if (moves.length && /위력|명중|수치|타입|정보|power|accuracy|type/i.test(query)) return moveFacts(result, moves);
  if (pokemon && (/뭐야|무엇|정보|도감|타입|종족치|스탯|능력치|공격|방어|스피드|특수|speed|attack|defense|special|\bhp\b/i.test(query) || key(query) === key(pokemon.name_ko) || key(query) === key(pokemon.name) || /^(?:#\s*)?\d{1,3}(?:\s*번)?$/.test(query))) return pokemonFacts(result, pokemon, query, store);
  if (/타입.*(?:뭐|뜻)|상성.*(?:뭐|뜻)/.test(query)) return { ...result, status: "partial", title: "개념 원문 연결 필요", answer: "타입 이름·기본 관계표는 조회할 수 있지만, 이 개념을 설명하는 검수 원문은 아직 연결하지 못했어요.", sources: [source("정형 타입 목록", "types.json", "이름 목록이며 개념 설명 원문 아님")] };
  const namedTypes = store.types.filter(row => new RegExp(`${escape(row.name_ko)}\\s*타입|\\b${escape(row.name)}\\b`, "i").test(query));
  if (namedTypes.length && !pokemonEntities.length && !moveEntities.length) {
    result.status = "answered"; result.title = "Red/Blue 타입 관계 조회";
    result.facts = namedTypes.length > 1 ? [`${namedTypes[0].name_ko} 공격 → ${namedTypes[1].name_ko} 방어: ${store.typeChart[namedTypes[0].name][namedTypes[1].name]}배`] : [`${namedTypes[0].name_ko} (${namedTypes[0].name}) · 타입 ID ${namedTypes[0].id}`];
    result.answer = result.facts.join(". ") + ". 관계를 물은 경우 첫 타입을 공격, 다음 타입을 방어로 읽은 로컬 조회예요.";
    result.sources = [source("정형 타입 조회", namedTypes.length > 1 ? "type_chart.json" : "types.json", "입력 순서의 공격→방어 관계")];
  }
  return result;
}
