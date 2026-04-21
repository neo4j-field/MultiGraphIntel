import datetime as _dt
import logging
import os
import urllib.parse
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from starlette.applications import Starlette
from starlette.routing import Mount

from neo4j import GraphDatabase, Driver
from neo4j.graph import Node, Relationship, Path
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger("intelligence-shim")

NEO4J_URI = os.environ["NEO4J_URI"]
NEO4J_USERNAME = os.environ["NEO4J_USERNAME"]
NEO4J_PASSWORD = os.environ["NEO4J_PASSWORD"]
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")
DEFAULT_ROW_LIMIT = int(os.getenv("NEO4J_DEFAULT_ROW_LIMIT", "100"))
HARD_ROW_LIMIT = int(os.getenv("NEO4J_HARD_ROW_LIMIT", "1000"))

driver: Driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))

FRAUDGRAPH_SCHEMA_HINT = """
Neo4j Intelligence graph schema (database: neo4j on Aura 27ad415a).

CRITICAL TYPE NOTES (common source of empty results):
  - Account.id is INT. Pass as an integer: {"id": 101}, NOT {"id": "101"}.
  - Person.id is INT. Same rule.
  - Card.card_id and Case.case_id are STRINGs.
  - If your query returns zero rows and you passed an id, the most likely
    cause is a string/int mismatch on the parameter.

Node labels and properties:
  Person   (id INT PK, name STRING, country STRING)
  Account  (id INT PK, is_active BOOL, account_type STRING,
            community_id INT, pagerank_score FLOAT, fraud_score FLOAT)
  Card     (card_id STRING PK, card_type STRING, country STRING, fraud_count INT)
  Case     (case_id STRING PK, opened_at DATETIME, status STRING,
            analyst STRING, summary STRING, recommended_action STRING)

Relationship types:
  (:Person)-[:OWNS]->(:Account)
  (:Account)-[:TRANSFERS {transaction_id, amount, transaction_type, at}]->(:Account)
  (:Account)-[:SUSPECTED_LAUNDERING_RING {ring_id}]->(:Account)
  (:Account)-[:LINKED_TO_CARD]->(:Card)
  (:Case)-[:INVESTIGATES]->(:Account)

Do NOT invent these. They do not exist in this graph:
  - (:Community) label           (community is a property, not a node)
  - [:HAS_CASE], [:BELONGS_TO]   (use [:INVESTIGATES] from Case to Account)

Worked examples you can adapt verbatim.

Community + open case for an account (this is the canonical demo query):
  Cypher:
    MATCH (a:Account {id: $id})
    OPTIONAL MATCH (c:Case {status: 'OPEN'})-[:INVESTIGATES]->(a)
    RETURN a.community_id AS community_id,
           a.fraud_score  AS fraud_score,
           c.case_id      AS case_id,
           c.analyst      AS analyst,
           c.recommended_action AS recommended_action
  Parameters:
    {"id": 101}

Suspected laundering ring touching an account:
  Cypher:
    MATCH p = (a:Account {id: $id})-[:SUSPECTED_LAUNDERING_RING*1..6]->(a)
    RETURN [n IN nodes(p) | n.id] AS ring_path,
           [r IN relationships(p) | r.ring_id][0] AS ring_id
  Parameters:
    {"id": 101}

Cross-substrate card links from accounts to BigQuery FraudGraph cards:
  Cypher:
    MATCH (a:Account)-[:LINKED_TO_CARD]->(k:Card)
    RETURN a.id AS account_id, k.card_id AS card_id,
           k.card_type AS card_type, k.fraud_count AS fraud_count
    ORDER BY k.fraud_count DESC
  Parameters:
    {}

Graph Data Science (GDS) algorithms are available. Use them in stream mode
so results flow back to you without mutating the stored graph.

GDS standard workflow (project, run, drop):
  Step 1 - Project an in-memory graph over the Account transfer network:
    CALL gds.graph.project(
      'accounts_transfers',
      'Account',
      {TRANSFERS: {orientation: 'NATURAL', properties: ['amount']}}
    )
    Parameters: {}

  Step 2a - Louvain community detection (streams communityId per node):
    CALL gds.louvain.stream('accounts_transfers')
    YIELD nodeId, communityId, intermediateCommunityIds
    RETURN gds.util.asNode(nodeId).id AS account_id,
           communityId
    ORDER BY communityId, account_id
    Parameters: {}

  Step 2b - PageRank (streams influence score per node):
    CALL gds.pageRank.stream('accounts_transfers')
    YIELD nodeId, score
    RETURN gds.util.asNode(nodeId).id AS account_id,
           score
    ORDER BY score DESC
    Parameters: {}

  Step 2c - Weakly Connected Components (find isolated clusters):
    CALL gds.wcc.stream('accounts_transfers')
    YIELD nodeId, componentId
    RETURN componentId, collect(gds.util.asNode(nodeId).id) AS accounts
    ORDER BY size(accounts) DESC
    Parameters: {}

  Step 3 - Drop the in-memory projection when finished:
    CALL gds.graph.drop('accounts_transfers', false)
    Parameters: {}

Constraints: this shim is read-only with respect to the stored graph.
CREATE/MERGE/SET/DELETE/REMOVE on stored data and any gds.*.write procedures
are rejected at the shim boundary. GDS stream, stats, mutate, project, and
drop are permitted because they only affect the in-memory catalog. Use the
Analytical or Operational agents for anything that belongs in BigQuery or
Spanner instead.
""".strip()

import re

# Raw-Cypher write keywords that mutate the stored graph directly.
RAW_WRITE_KEYWORDS = (
    "CREATE", "MERGE", "SET", "DELETE", "REMOVE",
    "FOREACH", "LOAD", "USING PERIODIC",
)

# Procedure-level patterns that mutate the stored graph through CALL.
# gds.*.write/writeNodeProperties/writeRelationship persist results back
# to the on-disk Neo4j graph, so they are rejected. gds.graph.project and
# gds.graph.drop operate on the in-memory graph catalog only and are safe.
FORBIDDEN_CALL_PATTERNS = [
    re.compile(r"\bCALL\s+GDS\.[\w.]*\.WRITE(NODEPROPERTIES|RELATIONSHIP|RELATIONSHIPTYPE)?\b", re.IGNORECASE),
    re.compile(r"\bCALL\s+APOC\.[\w.]*\.(CREATE|DELETE|SET|REMOVE|MERGE)\b", re.IGNORECASE),
    re.compile(r"\bCALL\s+DB\.[\w.]*\.(CREATE|DROP|DELETE)\b", re.IGNORECASE),
    re.compile(r"\bCALL\s+DBMS\.", re.IGNORECASE),
]

# Regex that recognises the raw-Cypher keywords as standalone tokens, so the
# substring "CREATE" inside a string literal or a GDS graph name like
# "createdAt_index" does not false-positive.
RAW_WRITE_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in RAW_WRITE_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


def _strip_string_literals(cypher: str) -> str:
    """Remove single- and double-quoted strings so keyword detection does not
    misfire on identifiers or labels that happen to contain write words."""
    without_single = re.sub(r"'(?:\\.|[^'\\])*'", "''", cypher)
    without_double = re.sub(r'"(?:\\.|[^"\\])*"', '""', without_single)
    return without_double


def _looks_like_write(cypher: str) -> bool:
    scrubbed = _strip_string_literals(cypher)
    if RAW_WRITE_RE.search(scrubbed):
        return True
    for pattern in FORBIDDEN_CALL_PATTERNS:
        if pattern.search(scrubbed):
            return True
    return False


def _serialize(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return value.isoformat()
    if isinstance(value, Node):
        return {
            "_type": "node",
            "labels": list(value.labels),
            "properties": {k: _serialize(v) for k, v in value.items()},
        }
    if isinstance(value, Relationship):
        return {
            "_type": "relationship",
            "type": value.type,
            "properties": {k: _serialize(v) for k, v in value.items()},
        }
    if isinstance(value, Path):
        return {
            "_type": "path",
            "nodes": [_serialize(n) for n in value.nodes],
            "relationships": [_serialize(r) for r in value.relationships],
        }
    if isinstance(value, dict):
        return {str(k): _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialize(v) for v in value]
    return str(value)


def _run_cypher(cypher: str, parameters: Optional[dict], row_limit: int) -> list[dict]:
    if _looks_like_write(cypher):
        raise ValueError(
            "The intelligence shim is read-only. This Cypher appears to mutate "
            "state, which is rejected. Rewrite the query using only MATCH, "
            "OPTIONAL MATCH, WITH, UNWIND, RETURN, and read-only CALL subqueries."
        )
    effective_limit = max(1, min(row_limit, HARD_ROW_LIMIT))
    logger.info(
        "Running Cypher (limit=%d params=%s): %s",
        effective_limit,
        parameters or {},
        cypher.replace("\n", " \\ "),
    )
    with driver.session(database=NEO4J_DATABASE, default_access_mode="READ") as session:
        result = session.run(cypher, parameters or {})
        rows: list[dict] = []
        for record in result:
            if len(rows) >= effective_limit:
                break
            rows.append({key: _serialize(record[key]) for key in record.keys()})
    logger.info("Cypher returned %d rows", len(rows))
    return rows


mcp = FastMCP(
    name="intelligence-graph-shim",
    instructions=(
        "Neo4j Aura + GDS intelligence tools for reasoning, community detection, "
        "and analyst memory. Call describe_schema first if unsure, then run_cypher "
        "with read-only Cypher against the Person/Account/Card/Case model."
    ),
    stateless_http=True,
    json_response=True,
)


@mcp.tool()
def describe_schema() -> str:
    """Return the Neo4j Intelligence graph schema and query idioms.

    Call this first when you are unsure about node labels, relationship
    types, or how to phrase a query. The returned string is the authoritative
    schema for this Aura instance, including the enrichment properties
    (community_id, pagerank_score, fraud_score) and the Case/Ring/Card-bridge
    relationships that are only available here.
    """
    return FRAUDGRAPH_SCHEMA_HINT


_ENTITY_LABELS = {
    "account": ("Account", "id"),
    "person":  ("Person",  "id"),
    "card":    ("Card",    "card_id"),
    "case":    ("Case",    "case_id"),
}


@mcp.tool()
def bloom_deeplink(entity_type: str, entity_id: str) -> dict:
    """Return a Neo4j Workspace Explore (Bloom) deep-link for the given entity.

    Use this whenever the user asks for a visual representation, says phrases
    like "show me in Bloom", "open this in Explore", "let me see the graph",
    or asks to explore a specific account, person, card, or case visually.

    Parameters:
      entity_type - one of: account, person, card, case.
      entity_id   - the natural id on that label. Account and Person use an
                    integer-like id (pass as string). Card uses CARD-NNNNN.
                    Case uses CASE-YYYY-MM-DD.

    Returns a dict:
      bloom_url        - Workspace Explore URL pre-wired to this Aura instance.
                         The user clicks it, signs in to Aura if needed, and
                         lands on the Explore tab for database "neo4j".
      suggested_search - the phrase to paste into the Explore search bar once
                         the page loads (e.g. "Account 101", "CASE-2026-04-15").
      note             - one-line instruction the agent can narrate to the user.

    The URL degrades gracefully: if Neo4j rotates Workspace parameter names,
    the user lands on workspace.neo4j.io and selects the database manually.
    """
    key = entity_type.strip().lower()
    if key not in _ENTITY_LABELS:
        raise ValueError(
            f"Unknown entity_type: {entity_type!r}. "
            f"Expected one of: {', '.join(_ENTITY_LABELS)}."
        )
    label, _ = _ENTITY_LABELS[key]

    # Workspace Explore accepts the full Neo4j connection URI on the
    # connectURL query param. Keep NEO4J_URI as the source of truth so this
    # travels with the shim across Aura instances.
    params = urllib.parse.urlencode({
        "connectURL": NEO4J_URI,
        "dbName":     NEO4J_DATABASE,
        "ntid":       NEO4J_USERNAME,
    })
    bloom_url = f"https://workspace.neo4j.io/workspace/explore?{params}"

    # Card and Case already carry human-readable ids (CARD-00050, CASE-...),
    # so we leave them alone. Account and Person get the label prefixed.
    if key in ("card", "case"):
        suggested_search = str(entity_id).strip()
    else:
        suggested_search = f"{label} {str(entity_id).strip()}"

    return {
        "bloom_url": bloom_url,
        "suggested_search": suggested_search,
        "note": (
            "Open the link, sign in to Aura if prompted, then paste the "
            "suggested search phrase into the Explore search bar to focus "
            "the graph on this entity."
        ),
    }


@mcp.tool()
def run_cypher(cypher: str, parameters: Optional[dict] = None, row_limit: int = DEFAULT_ROW_LIMIT) -> list[dict]:
    """Execute a read-only Cypher query against the Neo4j Intelligence graph.

    Parameters:
      cypher      - A read-only Cypher statement. Write-side keywords (CREATE,
                    MERGE, SET, DELETE, REMOVE, DROP, FOREACH, LOAD, mutating
                    procedure calls) are rejected by the shim.
      parameters  - Optional dict of Cypher parameters referenced via $name
                    syntax in the query. Prefer parameters over string
                    interpolation.
      row_limit   - Maximum rows to return (default 100, hard cap 1000).

    Returns a list of row dictionaries. Nodes, relationships, and paths are
    serialised to JSON-friendly dicts with _type markers.

    On errors the tool raises ValueError carrying both the Neo4j error text
    and the full schema reference, so you can revise the query and retry.

    Prefer the patterns listed by describe_schema. Do not invent labels such
    as :Community - the community is stored as Account.community_id.
    """
    try:
        return _run_cypher(cypher, parameters, row_limit)
    except ValueError:
        raise
    except Exception as exc:
        logger.warning("Cypher failed: %s", exc)
        raise ValueError(
            f"Neo4j error: {exc}. Revise the query using this reference:\n{FRAUDGRAPH_SCHEMA_HINT}"
        ) from exc


# ---------------------------------------------------------------------------
# REST surface for human debugging. Not consumed by the Vertex AI agent.
# ---------------------------------------------------------------------------

rest = FastAPI(title="Neo4j Intelligence Shim (REST)")


class CypherRequest(BaseModel):
    cypher: str
    parameters: Optional[dict] = None
    row_limit: Optional[int] = DEFAULT_ROW_LIMIT


@rest.get("/health")
def health() -> dict:
    try:
        with driver.session(database=NEO4J_DATABASE, default_access_mode="READ") as session:
            session.run("RETURN 1 AS ok").consume()
        return {"status": "healthy", "uri_host": NEO4J_URI.split("@")[-1]}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Neo4j unreachable: {exc}") from exc


@rest.get("/schema")
def rest_schema() -> dict:
    return {"schema": FRAUDGRAPH_SCHEMA_HINT}


@rest.post("/query")
def rest_query(request: CypherRequest) -> dict:
    try:
        rows = run_cypher(request.cypher, request.parameters, request.row_limit or DEFAULT_ROW_LIMIT)
        return {"rows": rows}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@asynccontextmanager
async def lifespan(app: Starlette):
    async with mcp.session_manager.run():
        try:
            yield
        finally:
            driver.close()


app = Starlette(
    lifespan=lifespan,
    routes=[
        Mount("/api", app=rest),
        Mount("/", app=mcp.streamable_http_app()),
    ],
)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
