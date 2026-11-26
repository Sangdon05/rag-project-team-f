/** Evidence-bounded suggestions for the local preview, never live agent output.
 * Every proposal is checked by the existing lookup module without changing state.
 */
import { answerPreview, detectEntities } from "./flow-preview.mjs";

const clean = value => String(value ?? "").normalize("NFC").trim();
const key = value => clean(value).toLowerCase().replace(/[\s\p{P}\p{S}]/gu, "");
const rows = value => Array.isArray(value) ? value : [];
const overlap = (left, right) => [...left].some(value => right.has(value));
const identity = entity => `${entity.kind}:${entity.id}`;
const mutableConditions = context => JSON.stringify({
  game: context?.game, opponentId: context?.opponentId ?? null,
  candidates: rows(context?.candidates).map(row => ({ id: row.id, moves: rows(row.moves) })),
  conditions: context?.conditions ?? {},
});

function phrase(persona, kind, name, target) {
  const variants = {
    profile: [`${name} 뭐야?`, `${name} 기본 정보부터 볼래`, `${name} 도감 정보 어떻게 됨?`],
    weakness: [`${name} 약점은 뭐야?`, `${name} 약점부터 볼래`, `${name} 방어 상성 어떻게 됨?`],
    learn: [`${name} 무슨 공격 배워?`, `${name}는 어떤 기술을 배워?`, `${name} 기술 습득표 어떻게 됨?`],
    values: [`${name} 정보 보고 싶어. 힘이랑 잘 맞는 정도는?`, `${name} 위력이랑 명중률은?`, `${name} 위력·명중률·PP 수치 어떻게 됨?`],
    compare: [`${name} 지금 가진 공격은 ${target}한테 얼마나 통해?`, `${name} 현재 기술로 ${target} 상대하면 뭐 써? 기본 타입 상성으로 비교해줘`, `${name} 현재 기술로 ${target} 상대 기본 타입 배율 비교하면 어떻게 됨?`],
  };
  return variants[kind]?.[persona === "P3" ? 2 : persona === "P2" ? 1 : 0] ?? "";
}

/** At most three answerable next questions; no preparation action or mutations.
 * context is the current/variant session, not a freshly substituted S01 example.
 */
export function suggestQuestions({ result, question, history, node, savedQuestions, personaId, context, store } = {}) {
  if (!store?.pokemonById || !store?.movesById || !Array.isArray(store.aliases) || !result) return [];
  const current = structuredClone(result.context ?? context ?? {
    game: "red-blue", mode: "custom", opponentId: null, candidates: [], comparisonBasis: null,
  });
  if (current.game !== "red-blue") return [];
  const persona = ["P1", "P2", "P3"].includes(personaId) ? personaId : "P2";
  const entities = value => detectEntities(clean(value), store);
  const focus = entities(question);
  const focusIds = new Set(focus.map(identity));
  const successful = result.status === "answered";
  // A successful answer may introduce a sourced related entity. An error's
  // inherited active Pokemon must not become an invented subject of the question.
  if (successful) {
    for (const entity of rows(result.entities)) focusIds.add(identity(entity));
    for (const row of rows(result.comparison)) {
      focusIds.add(`pokemon:${row.pokemonId}`); focusIds.add(`move:${row.moveId}`);
    }
    // baseResult also inherits activePokemonId for unrelated move queries.
    // Only promote that ID when the actual sourced answer names its Pokemon.
    const namedPokemon = store.pokemonById.get(result.pokemonId);
    if (namedPokemon && [result.title, ...rows(result.facts)].some(value =>
      entities(value).some(entity => entity.kind === "pokemon" && entity.id === namedPokemon.id))) {
      focusIds.add(`pokemon:${namedPokemon.id}`);
    }
  }
  if (!focusIds.size) return [];
  const candidates = rows(current.candidates);
  const target = store.pokemonById.get(current.opponentId);
  const preview = proposal => {
    try {
      const answer = answerPreview(proposal, current, store);
      if (answer.status !== "answered" || !rows(answer.sources).length
        || mutableConditions(answer.context) !== mutableConditions(current)) return null;
      return answer;
    } catch { return null; }
  };

  // Treat alternative wording for the same facts as a repeat. Comparison keys
  // use the actual current-kit rows so a new opponent/move set remains distinct.
  const meaningKeys = (proposal, answer) => {
    const found = entities(proposal), p = found.filter(row => row.kind === "pokemon"), m = found.filter(row => row.kind === "move");
    const keys = [];
    if (/배워|배우|습득|레벨|learn/i.test(proposal)) keys.push(`learn:${p.map(row => row.id).sort().join()}:${m.map(row => row.id).sort().join()}`);
    else if (/약점|저항|방어\s*상성/.test(proposal)) keys.push(`weakness:${p.map(row => row.id).sort().join()}`);
    else if (!m.length && p.length && /뭐야|정보|도감|타입|스탯|종족치/.test(proposal)) keys.push(`profile:${p.map(row => row.id).sort().join()}`);
    if (m.length && /위력|명중|수치|잘\s*맞|힘|정보/.test(proposal)) keys.push(`values:${m.map(row => row.id).sort().join()}`);
    if (rows(answer?.comparison).length) keys.push(`compare:${answer.context?.opponentId}:${answer.comparison.map(row => `${row.pokemonId}:${row.moveId}`).sort().join()}`);
    return keys;
  };
  const already = new Set(), meanings = new Set();
  for (const item of [...rows(history), { question }]) {
    const previous = clean(typeof item === "string" ? item : item?.question);
    if (!previous) continue;
    already.add(key(previous));
    // A condition-changing question must use its actual answer: replaying it
    // after the change can no longer select a move that was just removed.
    const previousAnswer = key(previous) === key(question) ? result : preview(previous);
    for (const meaning of meaningKeys(previous, previousAnswer)) meanings.add(meaning);
  }
  const output = [];
  const add = (proposal, origin, requireRelated = true) => {
    proposal = clean(proposal);
    if (!proposal || already.has(key(proposal))) return;
    const found = entities(proposal), ids = new Set(found.map(identity));
    if (requireRelated && !overlap(focusIds, ids)) return;
    if (/없|미보유|제외|빼/.test(proposal) && found.some(row => row.kind === "move")) {
      const namedOwners = found.filter(row => row.kind === "pokemon").map(row => candidates.find(candidate => candidate.id === row.id));
      const namedMoves = found.filter(row => row.kind === "move");
      // A negative ownership claim is only known for a confirmed current kit.
      // Merely looking up Pikachu does not confirm owning one without a move.
      if (namedOwners.length !== 1 || !namedOwners[0]
        || namedMoves.some(move => rows(namedOwners[0].moves).includes(move.id))) return;
    }
    const answer = preview(proposal);
    if (!answer) return;
    // Source-backed lookup must still answer the requested move values, rather
    // than the preview interpreting native 'strong?' as a different comparison.
    if (found.some(row => row.kind === "move") && /위력|명중|잘\s*맞|힘/.test(proposal)
      && !/위력.*명중|명중.*위력/s.test(rows(answer.facts).join("\n"))) return;
    const units = meaningKeys(proposal, answer);
    if (units.some(unit => meanings.has(unit))) return;
    output.push({ question: proposal, origin }); already.add(key(proposal));
    for (const unit of units) meanings.add(unit);
  };
  const saved = Array.isArray(savedQuestions) ? savedQuestions : savedQuestions?.questions ?? savedQuestions?.candidates ?? [];
  for (const item of rows(saved)) {
    if (item.persona_id !== persona) continue;
    const found = entities(item.question);
    // Deictic 'these three' requires three confirmed candidates and a current
    // comparison, not merely the default example existing in memory.
    if (!found.length && (!successful || !rows(result.comparison).length || candidates.length !== 3)) continue;
    if (!successful && /비교|추천|누구|쎄|배율|자속/.test(item.question)) continue;
    add(item.question, "agent-example", found.length > 0);
  }

  const pokemonIds = [...focusIds].filter(id => id.startsWith("pokemon:")).map(id => Number(id.split(":")[1]));
  const moveIds = [...focusIds].filter(id => id.startsWith("move:")).map(id => Number(id.split(":")[1]));
  const owner = pokemonIds.map(id => candidates.find(row => row.id === id)).find(Boolean)
    ?? (successful ? candidates.find(row => row.id === result.selection?.pokemonId) : null);
  const ownerName = owner && store.pokemonById.get(owner.id)?.name_ko;
  const local = (kind, name, opponent) => add(phrase(persona, kind, name, opponent), "followup");

  // Reuse supported relationships from the actual answer. Generic comparison
  // prompts are made concrete only when both owner and opponent are confirmed.
  for (const followup of rows(result.followups)) {
    if (followup.action !== "ask") continue;
    const found = entities(followup.question);
    const move = found.find(row => row.kind === "move"), pokemon = found.find(row => row.kind === "pokemon");
    if (move && /위력|명중|수치/.test(followup.question)) local("values", move.name);
    else if (pokemon && /배워|습득/.test(followup.question)) local("learn", pokemon.name);
    else if (pokemon && /정보|도감|뭐야/.test(followup.question)) local("profile", pokemon.name);
    else if (successful && ownerName && target && /비교|상성/.test(followup.question)) local("compare", ownerName, target.name_ko);
  }
  for (const id of moveIds) {
    const move = store.movesById.get(id); if (move) local("values", move.name_ko || move.name);
  }
  for (const id of pokemonIds) {
    const pokemon = store.pokemonById.get(id); if (!pokemon) continue;
    local("weakness", pokemon.name_ko || pokemon.name);
    local("learn", pokemon.name_ko || pokemon.name);
    local("profile", pokemon.name_ko || pokemon.name);
  }
  if (successful && ownerName && target) local("compare", ownerName, target.name_ko);
  // Recovery lines are already local UI drafts; never call them Hermes output.
  for (const recovery of rows(node?.recoveryQuestions)) {
    const found = entities(recovery), move = found.find(row => row.kind === "move"), pokemon = found.find(row => row.kind === "pokemon");
    if (move && /위력|명중|수치/.test(recovery)) local("values", move.name);
    else if (pokemon && /약점/.test(recovery)) local("weakness", pokemon.name);
    else if (pokemon && /타입|정보/.test(recovery)) local("profile", pokemon.name);
  }
  return output.slice(0, 3);
}
