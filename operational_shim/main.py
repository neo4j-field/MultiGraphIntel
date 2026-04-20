import os
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from starlette.applications import Starlette
from starlette.routing import Mount

from google.cloud import spanner
from mcp.server.fastmcp import FastMCP

INSTANCE_ID = os.getenv("SPANNER_INSTANCE_ID", "spanner-graph-instance")
DATABASE_ID = os.getenv("SPANNER_DATABASE_ID", "spanner-graph-db")

spanner_client = spanner.Client()
database = spanner_client.instance(INSTANCE_ID).database(DATABASE_ID)


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
    with database.snapshot() as snapshot:
        results = snapshot.execute_sql(gql)
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
    """Execute an arbitrary GQL traversal against the FinGraph property graph.

    Use this for ad-hoc questions that the canned tools cannot answer, for
    example transfer patterns, fan-out detection, or multi-hop traversals.
    The query must target GRAPH FinGraph and must be read-only. Returns a list
    of row dictionaries keyed by the projected column names.
    """
    return _execute_gql(gql)


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
