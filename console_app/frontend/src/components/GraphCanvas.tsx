import { useEffect, useMemo, useState } from "react";
import { InteractiveNvlWrapper } from "@neo4j-nvl/react";
import type { Node as NvlBaseNode, Relationship as NvlBaseRel } from "@neo4j-nvl/base";
import type { Entity, EntityType } from "../lib/extractEntities";
import { fetchSubgraph } from "../lib/api";

interface GraphCanvasProps {
  entities: Entity[];
}

const LABEL_COLORS: Record<string, string> = {
  Account: "#4c8bf5",
  Person: "#50e3c2",
  Card: "#f59e0b",
  Case: "#ef4444",
};

const TYPE_COLORS: Record<string, string> = {
  OWNS: "#50e3c2",
  TRANSFERS: "#4c8bf5",
  SUSPECTED_LAUNDERING_RING: "#ef4444",
  INVESTIGATES: "#f59e0b",
  LINKED_TO_CARD: "#8a93a6",
};

export function GraphCanvas({ entities }: GraphCanvasProps) {
  const [nodes, setNodes] = useState<NvlBaseNode[]>([]);
  const [rels, setRels] = useState<NvlBaseRel[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const primary = useMemo(() => entities[0], [entities]);

  useEffect(() => {
    async function load() {
      if (!primary) return;
      setLoading(true);
      setError(null);
      try {
        const sub = await fetchSubgraph(primary.entityType as EntityType, primary.entityId, 2);
        const styledNodes: NvlBaseNode[] = sub.nodes.map((n) => ({
          id: n.id,
          captions: [{ value: n.caption, styles: ["bold"] }],
          color: LABEL_COLORS[n.labels[0] ?? ""] ?? "#8a93a6",
          size: 34,
        }));
        const styledRels: NvlBaseRel[] = sub.relationships.map((r) => ({
          id: r.id,
          from: r.from,
          to: r.to,
          captions: [{ value: r.type }],
          color: TYPE_COLORS[r.type] ?? "#6b7280",
          width: 2,
        }));
        setNodes(styledNodes);
        setRels(styledRels);
      } catch (err) {
        setError((err as Error).message);
        setNodes([]);
        setRels([]);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [primary?.entityType, primary?.entityId]);

  return (
    <div className="relative h-full w-full bg-neo-slate">
      <div className="absolute left-4 top-4 z-10 rounded-lg border border-neo-line bg-neo-panel/80 px-3 py-2 backdrop-blur">
        <div className="text-xs uppercase tracking-wider text-neo-muted">Focus</div>
        <div className="text-sm text-neo-ink">
          {primary ? `${primary.entityType} ${primary.entityId}` : "No entity yet"}
        </div>
        {loading && <div className="mt-1 text-[11px] text-neo-muted">Loading subgraph...</div>}
        {error && <div className="mt-1 text-[11px] text-red-400">{error}</div>}
      </div>

      {nodes.length === 0 ? (
        <div className="flex h-full w-full items-center justify-center text-neo-muted">
          <div className="text-center max-w-sm">
            <div className="text-sm">
              Ask a question that names an account, card, or case. The relevant subgraph will render here.
            </div>
          </div>
        </div>
      ) : (
        <InteractiveNvlWrapper
          nodes={nodes}
          rels={rels}
          nvlOptions={{
            initialZoom: 0.9,
            disableTelemetry: true,
            layout: "forceDirected",
          }}
          nvlCallbacks={{}}
          mouseEventCallbacks={{ onZoom: true, onPan: true, onDrag: true }}
        />
      )}
    </div>
  );
}
