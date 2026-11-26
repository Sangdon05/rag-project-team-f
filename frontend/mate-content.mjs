/** Local Korean conversation fixtures for Red/Blue. UI-independent and read-only. */
import { answerPreview, detectEntities } from "./flow-preview.mjs";
import { suggestQuestions } from "./conversation-suggestions.mjs";

export const MATE_PROFILES = Object.freeze([
  Object.freeze({
    id: "P2", name: "루키", subtitle: "30대 여성 · 입문자",
    description: "피카츄 정도는 알아. 배틀은 처음이라 뭐부터 보면 돼?",
    mateName: "이슬이", mateImage: "assets/mate/iseul-face.webp",
    greeting: "궁금한 것부터 하나씩 보자.",
    preferenceQuestion: "내 취향에 맞는 후보는?",
    starterQuestion: "내 현재 기술 목록은?", avatarPokemonId: 7,
  }),
  Object.freeze({
    id: "P1", name: "에이스", subtitle: "8세 남아 · 배틀 초보",
    description: "포켓몬 책이랑 만화 좋아해! 어떤 공격이 더 쎄?",
    mateName: "지우", mateImage: "assets/mate/jiwoo-face.webp",
    greeting: "어떤 포켓몬이 궁금해?",
    preferenceQuestion: "나한테 맞는 포켓몬은?",
    starterQuestion: "내 공격 목록은?", avatarPokemonId: 25,
  }),
  Object.freeze({
    id: "P3", name: "마스터", subtitle: "20대 남성 · 숙련자",
    description: "타입이랑 자속은 앎. 조건 바뀌면 뭐 쓰면 됨?",
    mateName: "웅이", mateImage: "assets/mate/woong-face.webp",
    greeting: "상대와 현재 기술부터 확인하자.",
    preferenceQuestion: "취향으로 후보 좁히면?",
    starterQuestion: "꼬부기 종족치는?", avatarPokemonId: 95,
  }),
]);

const MATES_BY_ID = new Map(MATE_PROFILES.map(profile => [profile.id, profile]));
export const getMateProfile = id => MATES_BY_ID.get(id);

const PREFERENCES = Object.freeze([
  { type: "water", label: "물", exampleId: 7 },
  { type: "electric", label: "전기", exampleId: 25 },
  { type: "fire", label: "불꽃", exampleId: 4 },
]);
const TOPICS = {
  taste: /취향|(?:나한테|내게)\s*맞|좋아할\s*만한|좋아하는\s*타입|(?:물|전기|불꽃)\s*타입(?:\s*(?:인\s*)?후보|(?:을|이|가)?\s*좋아)/u,
  choice: /(?:후보|지금\s*가진)\s*(?:포켓몬)?(?:들의|들|은|는)?\s*(?:목록|뭐|누구)|(?:내|현재)\s*(?:포켓몬(?:과|이|의)?\s*)?(?:기술|공격)(?:은|이|의)?\s*(?:목록|뭐|확인)/u,
  strategy: /필승|(?:무조건|반드시)\s*(?:이기|이길|이겨|승리)|승리\s*보장|이기는\s*조합/u,
  prepare: /싱글\s*배틀\s*(?:준비|전)(?:[^.?!]*(?:확인|정리|체크|뭐|어떻게|도와|싶어)|\s*[.?!]?$)/u,
};

const valuesOf = move => move?.values_by_version_group?.["red-blue"];
const pokemonName = (store, id) => store.pokemonById.get(id)?.name_ko;
const moveName = (store, id) => store.movesById.get(id)?.name_ko;
const typeName = (store, type) => store.typesByName.get(type)?.name_ko ?? type;
const typesOf = (store, pokemon) => pokemon.types_gen1.map(type => typeName(store, type)).join("·");
const ask = question => ({ action: "ask", question });
const conditionSource = {
  label: "배틀 준비 조건", path: "./flow-preview.mjs", detail: "현재 세션에서 확인한 후보와 기술. 기본 예시는 initialContext()의 체험 조건.",
};
const guideSource = {
  label: "싱글 배틀 준비 안내", path: "./battle-journey.mjs", detail: "상대 타입, 현재 기술, 기본 수치와 배율, 배틀 조건 확인 순서.",
};
const pokemonSource = (id, detail = "types_gen1") => ({
  label: "Red/Blue 포켓몬 도감", path: "../data/processed/pokemon.json", detail: `도감 ${id}번 · ${detail}`,
});
const key = value => String(value ?? "").normalize("NFC").replace(/[\s\p{P}\p{S}]/gu, "");
function hasBatchim(name) {
  const tail = name?.codePointAt(name.length - 1);
  return tail >= 0xac00 && tail <= 0xd7a3 && (tail - 0xac00) % 28 !== 0;
}
const topicParticle = name => name + (hasBatchim(name) ? "은" : "는");

function preferenceQuestions(personaId) {
  return PREFERENCES.map(({ label }) => personaId === "P1" ? `${label} 타입 후보 뭐 있어?`
    : personaId === "P3" ? `${label} 타입 후보 목록은?` : `${label} 타입 후보는?`);
}

/** Returns a narrow local topic response, or null to fall through to standard lookup. */
export function answerMateTopic({ question, context, store, personaId }) {
  if (!question || !context || context.game !== "red-blue" || !store) return null;
  // Explicit questions for another title go through the caller's game check.
  if (/스칼렛|바이올렛|레츠고|소드|실드|파이어레드|리프그린|챔피언스|브릴리언트|샤이닝|하트골드|소울실버|(?:fire\s*red|leaf\s*green|scarlet|violet|champions|bdsp)/iu.test(question)) return null;
  const topic = Object.keys(TOPICS).find(name => TOPICS[name].test(question));
  if (!topic) return null;
  const entities = detectEntities(question, store);
  const candidates = context.candidates ?? [];
  const pack = (title, answer, extra = {}) => ({
    status: "answered", title, answer, facts: [], sources: [], followups: [], entities,
    pokemonId: entities.find(row => row.kind === "pokemon")?.id ?? context.activePokemonId ?? null,
    context: structuredClone(context), storyTopic: topic, ...extra,
  });
  if (topic === "taste") {
    const preference = PREFERENCES.find(({ label }) => new RegExp(`${label}\\s*타입`, "u").test(question));
    const sample = preference ? [store.pokemonById.get(preference.exampleId)] : PREFERENCES.map(row => store.pokemonById.get(row.exampleId));
    const known = candidates.map(row => store.pokemonById.get(row.id)).filter(Boolean);
    const matching = known.filter(pokemon => !preference || pokemon.types_gen1.includes(preference.type));
    const listed = (matching.length ? matching : sample).filter(Boolean).slice(0, 3);
    if (!listed.length) return null;
    const facts = listed.map(pokemon => `${pokemon.name_ko} · ${typesOf(store, pokemon)} 타입`);
    if (listed.length === 1) facts.push(`도감 ${listed[0].id}번`);
    const options = listed.map(pokemon => ask(`${pokemon.name_ko} 도감 정보는?`));
    const scope = matching.length ? "지금 표시된 후보" : "체험용 도감 후보";
    const heading = preference ? `${scope}에서 찾은 ${preference.label} 타입이야.`
      : "좋아하는 타입을 하나 골라 봐.";
    return pack("취향에 맞는 포켓몬 둘러보기", `${heading}\n${facts.join("\n")}`, {
      facts, sources: listed.map(pokemon => pokemonSource(pokemon.id)),
      followups: preference ? options : preferenceQuestions(personaId).map(ask),
    });
  }
  if (topic === "choice") {
    const facts = candidates.map(({ id, moves }) => `${pokemonName(store, id) ?? "이름 미확인"} · ${moves.map(moveId => moveName(store, moveId)).filter(Boolean).join(" / ") || "현재 기술 미확인"}`);
    if (!facts.length) return pack("내 후보 확인", "배틀에 데려갈 포켓몬과 지금 쓸 수 있는 기술을 먼저 적어 줘.", { status: "needs_context" });
    if (facts.length === 1) facts.push("현재 기술과 배울 수 있는 기술은 따로 확인");
    return pack("내 후보와 현재 기술", `지금 확인한 목록이야.\n${facts.join("\n")}\n도감에서 배울 수 있는 기술은 여기의 현재 기술과 따로 봐야 해.`, {
      facts, sources: [conditionSource],
      followups: [ask("현재 기술의 기본 타입 상성을 비교해줘")],
    });
  }
  const target = store.pokemonById.get(context.opponentId);
  if (topic === "strategy") {
    const comparison = answerPreview(`${question}\n현재 기술의 기본 타입 상성을 비교해줘`, context, store);
    const lead = "한 조합이 꼭 이긴다고 판단할 수는 없어. 지금 가진 기술 중 상대에게 잘 통하는 공격부터 준비할 수 있어.";
    const detail = {
      facts: comparison.facts, sources: comparison.sources, context: comparison.context,
      comparison: comparison.comparison, selection: comparison.selection, clearSelection: comparison.clearSelection,
    };
    if (comparison.status !== "answered") return pack("유리한 조합을 볼 때 필요한 조건", `${lead}\n${comparison.answer}`, {
      ...detail, status: comparison.status,
    });
    return pack("기본 상성 기준의 유리한 조합", `${lead}\n${comparison.answer}`, {
      ...detail, status: "partial",
      followups: [ask("현재 기술의 기본 타입 상성을 비교해줘")],
    });
  }
  const selected = context.selection, owner = pokemonName(store, selected?.pokemonId), attack = moveName(store, selected?.moveId);
  const facts = [
    `상대 · ${target?.name_ko ?? "미확인"}`,
    `내 선택 · ${owner && attack ? `${owner}와 ${attack}` : "후보와 기술을 아직 고르지 않았어"}`,
    `남은 PP · ${context.conditions?.ppEnough === true ? "충분하다고 입력한 조건" : "게임에서 확인할 항목"}`,
  ];
  return pack("싱글 배틀 준비 전 확인", `상대, 지금 쓸 공격, 남은 PP를 확인하자.\n${facts.join("\n")}`, {
    status: target && candidates.some(row => row.moves.length) ? "answered" : "needs_context",
    facts, sources: [guideSource, conditionSource], followups: [ask("현재 기술의 기본 타입 상성을 비교해줘")],
  });
}

function simpleSpeech(value) {
  return String(value ?? "")
    .replaceAll("않았어요", "않았어").replaceAll("않아요", "않아")
    .replaceAll("없어요", "없어").replaceAll("있어요", "있어")
    .replaceAll("이에요", "이야").replaceAll("예요", "야")
    .replaceAll("줘요", "줘").replaceAll("돼요", "돼").replaceAll("해요", "해")
    .replaceAll("봤어요", "봤어").replaceAll("했어요", "했어");
}

function statLines(result, store, plain, includePp, includeType = false) {
  const ids = result.entities.filter(entity => entity.kind === "move").map(entity => entity.id);
  return [...new Set(ids)].slice(0, 2).flatMap(id => {
    const move = store.movesById.get(id), stats = valuesOf(move);
    if (!stats) return [];
    const power = stats.power == null ? "" : `${plain ? "기본 세기" : "기본 위력"} ${stats.power}`;
    const accuracy = stats.accuracy == null ? "" : `${plain ? "기본 맞히는 비율" : "기본 명중률"} ${stats.accuracy}%`;
    const pp = includePp && stats.pp != null ? `기본 PP ${stats.pp}` : "";
    const type = includeType ? `타입 ${typeName(store, stats.type)}` : "";
    const fields = [type, power, accuracy, pp].filter(Boolean);
    return fields.length ? [`${move.name_ko} · ${fields.join(", ")}`] : [];
  });
}

const sentences = text => simpleSpeech(text).split(/(?<=[.!?。])\s+|\n+/u).map(line => line.trim()).filter(Boolean);
const summary = (lead, facts) => [lead, ...facts.filter(Boolean).slice(0, 3).map(fact => `• ${fact}`)].join("\n");

/** One direct line, followed by up to three facts or next actions. */
export function formatMateAnswer({ result, question = "", personaId, store }) {
  const child = personaId === "P1", expert = personaId === "P3";
  const [first, ...rest] = sentences(result.answer);
  const target = store.pokemonById.get(result.context.opponentId);
  const rows = (result.comparison ?? []).filter(row => row.typeFactor != null);

  if (result.storyTopic === "strategy") {
    const best = rows.length ? Math.max(...rows.map(row => row.typeFactor)) : null;
    const strongest = rows.filter(row => row.typeFactor === best);
    const notes = strongest.length ? strongest.slice(0, 2).map(row =>
      `${pokemonName(store, row.pokemonId)} · ${moveName(store, row.moveId)}: ${row.typeFactor}배`) : rest;
    return summary(child ? "꼭 이기는 조합은 알 수 없어." : "승리는 보장할 수 없어.", [
      ...notes.slice(0, 2), rows.length ? "기준 · 현재 기술의 기본 타입 상성" : "상대와 현재 기술부터 확인",
    ]);
  }
  if (result.storyTopic) {
    const lead = result.storyTopic === "taste" && expert ? "타입으로 후보를 좁혀 보자." : first;
    return summary(lead, result.facts.length ? result.facts : rest);
  }

  if (result.status === "unconnected") {
    const lead = child ? "그건 도감에서 아직 못 찾았어!" : "이 질문에 해당하는 도감 근거가 없어.";
    return summary(lead, ["포켓몬 이름", "궁금한 기술 또는 상황"]);
  }
  if (result.status !== "answered") {
    if (result.title === "실제 대전 계산은 지원 밖") return summary("실제 피해와 승률은 계산할 수 없어.", [
      "비교 가능 · 기본 타입 배율", "비교 가능 · 같은 타입 보정(자속)",
    ]);
    return summary(first, rest.length ? rest : result.facts);
  }

  if (rows.length && target) {
    const chosen = rows.find(row => result.selection?.pokemonId === row.pokemonId && result.selection?.moveId === row.moveId);
    const includePp = /PP|피피/iu.test(question);
    const values = result.facts.some(fact => fact.includes("기본 위력")) ? statLines(result, store, child, includePp) : [];
    const showStab = expert || /자속|같은\s*타입/u.test(question);
    const display = rows.length > 2 && chosen ? [chosen] : rows.slice(0, 2);
    const facts = display.map(row => {
      const name = moveName(store, row.moveId);
      const value = values.find(line => line.startsWith(name + " · "))?.split(" · ")[1];
      const effect = row.typeFactor === 0 ? "0배 · 무효" : `타입 ${row.typeFactor}배`;
      const same = showStab ? `${child ? "같은 타입 보정" : "자속"} ${row.stab}배` : "";
      return [name, effect, same, value].filter(Boolean).join(" · ");
    });
    const chosenMove = chosen && moveName(store, chosen.moveId);
    const lead = chosenMove ? `기본 상성은 ${chosenMove}${hasBatchim(chosenMove) ? "이" : "가"} ${child ? "더 좋아!" : "유리해."}`
      : child ? `${target.name_ko}에게 얼마나 잘 통하는지 보자!`
        : expert ? `${target.name_ko} 상대 기본 배율이야.` : `${target.name_ko}에게 통하는 정도야.`;
    return summary(lead, [
      ...facts, showStab ? "기본 배율과 자속은 실제 피해량과 달라." : "기준 · 기본 타입 상성",
    ]);
  }

  if (result.title === "상대 정보와 현재 공격부터" && target) {
    return summary(child ? "먼저 상대부터 보자!" : "상대 타입과 내 기술부터 확인하자.", [
      `${target.name_ko} · ${typesOf(store, target)} 타입`, "다음 · 지금 쓸 수 있는 기술",
    ]);
  }
  if (result.title.includes("도감 조회")) {
    const record = store.pokemonById.get(result.pokemonId);
    if (record) {
      const stats = result.facts.slice(2);
      const facts = stats.length ? [
        stats.slice(0, 2).join(" · "), stats.slice(2, 4).join(" · "), stats.slice(4).join(" · "),
      ] : [`도감 ${record.id}번`, `타입 · ${typesOf(store, record)}`];
      if (stats.length === 1) facts[1] = `도감 ${record.id}번`;
      return summary(stats.length ? `${record.name_ko}의 기본 능력치야.`
        : `${topicParticle(record.name_ko)} ${typesOf(store, record)} 타입${child ? "이야!" : "이야."}`, facts);
    }
  }
  if (result.title.includes("기본 방어 상성")) {
    const resistance = /저항/u.test(question);
    const facts = result.facts.filter(fact => (resistance ? /배율 (?:0|0\.25|0\.5)$/ : /배율 (2|4)$/).test(fact));
    const label = resistance ? "덜 통하는 공격" : "잘 통하는 공격";
    if (facts.length) return summary(`${pokemonName(store, result.pokemonId)}에게 ${label}이야.`,
      facts.map(fact => fact.replace(": 기본 타입 배율 ", " · ") + "배"));
  }
  if (result.title === "Red/Blue 기술 수치") {
    const stats = statLines(result, store, child, /PP|피피/iu.test(question), /타입|정보/u.test(question));
    if (stats.length) return summary(child ? "공격의 기본 세기와 잘 맞는 정도야!"
      : expert ? "Red/Blue 기본 기술 수치야." : "기술의 기본 수치야.", [
      ...stats, "기본 위력과 실제 피해량은 달라.",
    ]);
  }
  if (result.title.includes("습득")) {
    const facts = result.facts.map(fact => fact.replace(": 기술머신·비전머신 방법 기록 (level=0은 레벨업 습득 아님)", " · 기술머신/비전머신"));
    if (result.facts.some(fact => fact.includes("레벨업 기록은 없음"))) {
      return summary("레벨을 올려서는 배우지 않아.", [
        facts[0], "기술머신을 갖고 있는지는 게임에서 확인",
      ]);
    }
    return summary(child ? "이런 공격을 배울 수 있어!" : "Red/Blue에서 배울 수 있는 기술이야.", facts);
  }
  return summary(first ?? "확인할 조건을 알려 줘.", result.facts.length ? result.facts : rest);
}

/** Suggest grounded questions without mutating inventory, selection or progress. */
export function suggestMateQuestions(args) {
  const { result, question, history, node, personaId, store } = args;
  if (!result || result.context?.game !== "red-blue" || !store) return [];
  const target = store.pokemonById.get(result.context.opponentId);
  const candidateReady = !!target && result.context.candidates.length > 0
    && result.context.candidates.every(row => row.moves.length > 0);
  const prior = new Set([question, ...(history ?? []).map(turn => turn.question)].map(key));
  const core = personaId === "P1" ? "지금 공격 뭐가 통해?" : "현재 기술 비교해줘";
  const recap = "싱글 배틀 준비 정리해줘";
  const typeMoves = personaId === "P1" ? "내 공격 목록은?" : "내 현재 기술 목록은?";
  const taste = getMateProfile(personaId)?.preferenceQuestion;
  const coreCandidate = result.context.candidates.find(row => row.id === result.context.activePokemonId)
    ?? result.context.candidates[0];
  const focus = result.selection?.moveId ?? result.entities.find(entity => entity.kind === "move")?.id
    ?? (result.storyTopic === "choice" ? coreCandidate?.moves[0] : null);
  const selectedMove = focus && moveName(store, focus);
  const values = selectedMove && !result.facts.some(fact => fact.includes("위력")) && (personaId === "P1"
    ? `${selectedMove} 정보는? 잘 맞아?` : `${selectedMove} 위력과 명중률은?`);
  const readiness = node?.id === "readiness";
  const path = result.storyTopic === "taste" ? [...result.followups.map(item => item.question), typeMoves]
    : result.storyTopic === "choice" ? [values, core, taste]
      : result.storyTopic === "strategy" || result.storyTopic === "prepare" ? [core, values, typeMoves]
        : result.title.includes("도감 조회") ? [typeMoves, values, core] : [readiness ? recap : "", values, core, taste];

  const picks = [];
  for (const proposal of path) {
    if (!proposal || prior.has(key(proposal))) continue;
    if ((proposal === core || proposal === recap) && !candidateReady) continue;
    const next = answerMateTopic({ question: proposal, context: result.context, store, personaId })
      ?? answerPreview(proposal, result.context, store);
    if (next.status !== "answered" || !next.sources.length) continue;
    picks.push({ question: proposal, origin: "followup" });
    prior.add(key(proposal));
  }
  const saved = suggestQuestions(args).filter(item => item.question.length <= 28 && !prior.has(key(item.question)));
  return [...picks, ...saved].slice(0, 3);
}
