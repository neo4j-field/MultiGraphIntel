"""Direct Neo4j queries that return NVL-ready subgraphs for visualization.

The router answer drives the narrative; this module powers the right-hand
NVL canvas. When the UI sees an account_id, case_id, or card_id in the
answer, it calls GET /subgraph with that entity and depth, and renders the
returned nodes/relationships in NVL without going through the LLM at all.
That keeps the graph view responsive and decouples visualization latency
from agent latency.
"""
from __future__ import annotations

from typing import Any, Optional

from neo4j import GraphDatabase, Driver

from .config import NEO4J_DATABASE, NEO4J_PASSWORD, NEO4J_URI, NEO4J_USERNAME


_driver: Optional[Driver] = None


def get_driver() -> Driver:
    global _driver
    if _driver is None:
        if not (NEO4J_URI and NEO4J_USERNAME and NEO4J_PASSWORD):
            raise RuntimeError("Neo4j credentials not configured (NEO4J_URI/USERNAME/PASSWORD).")
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
    return _driver


def close_driver() -> None:
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


def _node_payload(node) -> dict[str, Any]:
    return {
        "id": str(node.element_id),
        "labels": list(node.labels),
        "properties": _serialize_props(dict(node.items())),
        "caption": _caption_for(node),
    }


def _rel_payload(rel) -> dict[str, Any]:
    return {
        "id": str(rel.element_id),
        "from": str(rel.start_node.element_id),
        "to": str(rel.end_node.element_id),
        "type": rel.type,
        "properties": _serialize_props(dict(rel.items())),
        "caption": rel.type,
    }


def _serialize_props(props: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for k, v in props.items():
        try:
            if hasattr(v, "isoformat"):
                clean[k] = v.isoformat()
            elif isinstance(v, (str, int, float, bool)) or v is None:
                clean[k] = v
            else:
                clean[k] = str(v)
        except Exception:
            clean[k] = str(v)
    return clean


def _caption_for(node) -> str:
    props = dict(node.items())
    for key in ("id", "card_id", "case_id", "name"):
        if key in props and props[key] is not None:
            label = next(iter(node.labels), "Node")
            return f"{label} {props[key]}"
    return next(iter(node.labels), "Node")


def fetch_subgraph(entity_type: str, entity_id: str | int, depth: int = 1) -> dict[str, Any]:
    """Return all nodes and relationships within `depth` hops of the seed entity.

    entity_type is one of: account, person, card, case. entity_id is the
    natural id on that label (e.g. Account.id, Card.card_id). The result is
    an NVL-friendly payload with nodes[] and relationships[].
    """
    depth = max(1, min(depth, 3))
    label_by_entity = {
        "account": ("Account", "id", int),
        "person": ("Person", "id", int),
        "card": ("Card", "card_id", str),
        "case": ("Case", "case_id", str),
    }
    if entity_type not in label_by_entity:
        raise ValueError(f"Unknown entity_type: {entity_type}")
    label, prop, caster = label_by_entity[entity_type]
    try:
        entity_value: Any = caster(entity_id)
    except Exception as exc:
        raise ValueError(f"Invalid {entity_type} id: {entity_id!r}") from exc

    cypher = (
        f"MATCH (seed:{label} {{{prop}: $value}}) "
        "OPTIONAL MATCH path = (seed)-[*1.."
        f"{depth}]-(neighbour) "
        "WITH collect(DISTINCT seed) + collect(DISTINCT neighbour) AS ns, "
        "     collect(DISTINCT path) AS ps "
        "UNWIND ns AS n WITH ns, ps, n WHERE n IS NOT NULL "
        "WITH collect(DISTINCT n) AS nodes, ps "
        "UNWIND ps AS p WITH nodes, p WHERE p IS NOT NULL "
        "UNWIND relationships(p) AS r "
        "RETURN nodes, collect(DISTINCT r) AS rels"
    )

    driver = get_driver()
    with driver.session(database=NEO4J_DATABASE, default_access_mode="READ") as session:
        result = session.run(cypher, value=entity_value)
        record = result.single()
        if record is None:
            return {"nodes": [], "relationships": []}
        nodes = [_node_payload(n) for n in (record["nodes"] or [])]
        rels = [_rel_payload(r) for r in (record["rels"] or [])]
        return {"nodes": nodes, "relationships": rels}
