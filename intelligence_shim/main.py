import datetime as _dt
import logging
import os
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
Neo4j Intelligence graph schema (database: neo4j on Aura 27ad415a):

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

Query idioms to prefer:
  - Use parameters with $name syntax, not string interpolation.
  - Read the community as a property: (a:Account).community_id, not a (:Community) label.
  - For the laundering ring use: MATCH p = (a:Account)-[:SUSPECTED_LAUNDERING_RING*]->(a)
  - For an analyst case on an account use:
      MATCH (c:Case)-[:INVESTIGATES]->(a:Account {id: $id})
      RETURN c.case_id, c.analyst, c.summary, c.recommended_action
  - For cross-substrate card links use: (a:Account)-[:LINKED_TO_CARD]->(k:Card)

Constraint: this shim is read-only. CREATE, MERGE, SET, DELETE, REMOVE, and
procedure calls that mutate state are rejected at the shim boundary. Use the
Analytical or Operational agents for anything that belongs in BigQuery or
Spanner instead.
""".strip()

WRITE_KEYWORDS = {
    "CREATE", "MERGE", "SET", "DELETE", "REMOVE", "DROP",
    "FOREACH", "LOAD", "USING PERIODIC",
}


def _looks_like_write(cypher: str) -> bool:
    upper = cypher.upper()
    for keyword in WRITE_KEYWORDS:
        if keyword in upper:
            return True
    # Block side-effecting CALL procedures. Allow CALL {...} subqueries that
    # are purely read-only by checking for a non-subquery CALL followed by an
    # identifier (e.g. db.create, apoc.create, dbms.security.createUser).
    if "CALL " in upper:
        for bad in (".CREATE", ".DELETE", ".SET", ".REMOVE", ".CLEAR", ".MERGE"):
            if bad in upper:
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
        bool(parameters),
        cypher.replace("\n", " \\ "),
    )
    with driver.session(database=NEO4J_DATABASE, default_access_mode="READ") as session:
        result = session.run(cypher, parameters or {})
        rows: list[dict] = []
        for record in result:
            if len(rows) >= effective_limit:
                break
            rows.append({key: _serialize(record[key]) for key in record.keys()})
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
