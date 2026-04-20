// Heuristic entity extraction from agent text. The router answer includes
// ids like "account 101", "Account 104", "CASE-2026-04-15", "CARD-00050".
// We pull the first few of each so the graph canvas can render the
// subgraph relevant to the conversation without another LLM call.

export type EntityType = "account" | "person" | "card" | "case";

export interface Entity {
  entityType: EntityType;
  entityId: string;
}

export function extractEntities(text: string): Entity[] {
  const found: Entity[] = [];
  const seen = new Set<string>();

  const patterns: { type: EntityType; regex: RegExp }[] = [
    { type: "account", regex: /account(?:_id)?[\s#:]*([0-9]{2,6})/gi },
    { type: "person", regex: /person(?:_id)?[\s#:]*([0-9]{1,6})/gi },
    { type: "card", regex: /\b(CARD-[0-9]{3,6})\b/gi },
    { type: "case", regex: /\b(CASE-[0-9]{4}-[0-9]{2}-[0-9]{2})\b/gi },
  ];

  for (const { type, regex } of patterns) {
    const matches = text.matchAll(regex);
    for (const m of matches) {
      const id = (m[1] ?? "").trim();
      if (!id) continue;
      const key = `${type}:${id}`;
      if (seen.has(key)) continue;
      seen.add(key);
      found.push({ entityType: type, entityId: id });
    }
  }

  return found;
}
