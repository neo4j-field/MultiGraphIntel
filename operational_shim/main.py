import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from starlette.applications import Starlette
from starlette.routing import Mount

from google.cloud import spanner
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger("operational-shim")

INSTANCE_ID = os.getenv("SPANNER_INSTANCE_ID", "spanner-graph-instance")
DATABASE_ID = os.getenv("SPANNER_DATABASE_ID", "spanner-graph-db")

spanner_client = spanner.Client()
database = spanner_client.instance(INSTANCE_ID).database(DATABASE_ID)

FINGRAPH_SCHEMA_HINT = """
Spanner Graph FinGraph schema:
  Nodes:
    Person    (id INT64 PK, name STRING, country STRING)
    Account   (id INT64 PK, is_active BOOL, account_type STRING, create_time TIMESTAMP)
  Edges:
    (:Person)-[:Owns]->(:Account)
    (:Account)-[t:Transfers {amount FLOAT64, create_time TIMESTAMP, transaction_id STRING, transaction_type STRING}]->(:Account)

Spanner GQL rules to remember:
  - Every query MUST begin with: GRAPH FinGraph
  - MATCH and RETURN are required; use AS to alias projections.
  - Parameters use @name syntax, not $name (Cypher style).
  - Do not use Cypher-only features like toInteger(), CALL, or WITH.

Working example (direct outgoing transfers from account 101):
  GRAPH FinGraph
  MATCH (a:Account {id: 101})-[t:Transfers]->(b:Account)
  RETURN a.id AS from_id, b.id AS to_id, t.amount AS amount, t.transaction_type AS type
""".strip()


def _ensure_graph_prefix(gql: str) -> str:
    """Prepend GRAPH FinGraph if the caller omitted it."""
    stripped = gql.lstrip()
    first_line = stripped.split("\n", 1)[0].strip().upper()
    if first_line.startswith("GRAPH "):
        return gql
    return "GRAPH FinGraph\n" + gql


def _row_to_dict(fields, row) -> dict:
    return {field.name: value for field, value in zip(fields, row)}


def _query_account(account_id: int) -> Optional[dict]:
    gql = """
    GRAPH FinGraph
    MATCH (a:Account {id: @account_id})
    RETURN a.id AS id, a.is_active AS is_active, a.account_type AS account_type
    """
    params = {"account_id": account_id}
    param_types = {"account_id": spanner.param_types.INT64}
    with database.snapshot() as snapshot:
        results = snapshot.execute_sql(gql, params=params, param_types=param_types)
        rows = list(results)
        if not rows:
            return None
        return _row_to_dict(results.fields, rows[0])


def _query_person_network(person_id: int) -> list[dict]:
    gql = """
    GRAPH FinGraph
    MATCH (p:Person {id: @person_id})-[:Owns]->(a:Account)
    RETURN p.name AS person_name, a.id AS account_id, a.is_active AS is_active
    """
    params = {"person_id": person_id}
    param_types = {"person_id": spanner.param_types.INT64}
    with database.snapshot() as snapshot:
        results = snapshot.execute_sql(gql, params=params, param_types=param_types)
        rows = list(results)
        return [_row_to_dict(results.fields, row) for row in rows]


def _execute_gql(gql: str) -> list[dict]:
    effective_gql = _ensure_graph_prefix(gql)
    logger.info("Executing GQL: %s", effective_gql.replace("\n", " \\ "))
    with database.snapshot() as snapshot:
        results = snapshot.execute_sql(effective_gql)
        rows = list(results)
        return [_row_to_dict(results.fields, row) for row in rows]


mcp = FastMCP(
    name="operational-graph-shim",
    instructions=(
        "Live, low-latency Spanner Graph tools over the FinGraph property graph. "
        "Use these tools to answer questions about current account status, direct "
        "ownership relationships, and ad-hoc GQL traversals."
    ),
    stateless_http=True,
    json_response=True,
)


@mcp.tool()
def get_account(account_id: int) -> dict:
    """Return live status for a given account id from Spanner FinGraph.

    Use this for point lookups such as "is account 101 currently active".
    Returns id, is_active, and account_type. Raises if the account does not exist.
    """
    account = _query_account(account_id)
    if account is None:
        raise ValueError(f"Account {account_id} not found in FinGraph")
    return account


@mcp.tool()
def get_person_network(person_id: int) -> list[dict]:
    """Return the accounts directly owned by a given person from Spanner FinGraph.

    Use this to answer "which accounts does person X own" or to bootstrap a
    one-hop neighbourhood. Returns a list of rows with person_name, account_id,
    and is_active.
    """
    return _query_person_network(person_id)


@mcp.tool()
def execute_gql(gql: str) -> list[dict]:
    """Execute a Spanner Graph GQL query against the FinGraph property graph.

    IMPORTANT: this is Spanner GQL, not Cypher. The query must begin with
    `GRAPH FinGraph` (the shim will prepend it if you forget). Use @param
    syntax for parameters, not $param. Do not use Cypher-only clauses such
    as WITH, CALL, or toInteger().

    Schema and syntax reference:

    Nodes:
      Person  (id, name, country)
      Account (id, is_active, account_type, create_time)
    Edges:
      (:Person)-[:Owns]->(:Account)
      (:Account)-[t:Transfers {amount, create_time, transaction_id, transaction_type}]->(:Account)

    Working example - outgoing transfers from account 101:
      GRAPH FinGraph
      MATCH (a:Account {id: 101})-[t:Transfers]->(b:Account)
      RETURN a.id AS from_id, b.id AS to_id, t.amount AS amount, t.transaction_type AS type

    Returns a list of row dictionaries keyed by projected column names. On
    syntax errors the tool raises ValueError with the Spanner error text and
    the schema hint, so you can revise and retry.
    """
    try:
        return _execute_gql(gql)
    except Exception as exc:
        logger.warning("GQL failed: %s", exc)
        raise ValueError(
            f"Spanner GQL error: {exc}. Revise the query using this reference:\n{FINGRAPH_SCHEMA_HINT}"
        ) from exc


@mcp.tool()
def describe_graph_schema() -> str:
    """Return the FinGraph node labels, edge types, properties, and Spanner GQL syntax rules.

    Call this first if you are unsure how to phrase a GQL query. The returned
    string includes the authoritative schema and a working example you can
    adapt.
    """
    return FINGRAPH_SCHEMA_HINT


rest = FastAPI(title="Spanner Graph Operational Shim (REST)")


class GQLRequest(BaseModel):
    gql: str


@rest.get("/health")
def health() -> dict:
    return {"status": "healthy"}


@rest.get("/account/{account_id}")
def rest_get_account(account_id: int) -> dict:
    account = _query_account(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@rest.get("/person/{person_id}/network")
def rest_get_person_network(person_id: int) -> dict:
    return {"network": _query_person_network(person_id)}


@rest.post("/query")
def rest_execute_gql(request: GQLRequest) -> dict:
    try:
        return {"results": _execute_gql(request.gql)}
    except Exception as exc:  # surface Spanner errors to the caller
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@asynccontextmanager
async def lifespan(app: Starlette):
    async with mcp.session_manager.run():
        yield


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
