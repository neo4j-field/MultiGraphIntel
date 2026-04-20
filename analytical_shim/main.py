import datetime as _dt
import logging
import os
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from starlette.applications import Starlette
from starlette.routing import Mount

from google.cloud import bigquery
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger("analytical-shim")

PROJECT_ID = os.getenv("BQ_PROJECT_ID", "neo4jeventdemos")
DATASET_ID = os.getenv("BQ_DATASET_ID", "graph_intel_metadata")
MAX_BYTES_BILLED = int(os.getenv("BQ_MAX_BYTES_BILLED", str(1 * 1024 * 1024 * 1024)))  # 1 GiB
DEFAULT_ROW_LIMIT = int(os.getenv("BQ_DEFAULT_ROW_LIMIT", "100"))
HARD_ROW_LIMIT = int(os.getenv("BQ_HARD_ROW_LIMIT", "1000"))

bq_client = bigquery.Client(project=PROJECT_ID)

FRAUDGRAPH_SCHEMA_HINT = f"""
BigQuery FraudGraph schema (dataset: {PROJECT_ID}.{DATASET_ID}):

Node tables:
  Card        (card_id STRING PK, card_type STRING, country STRING, issuer STRING)
  Transaction (transaction_id STRING PK, time_seconds FLOAT64, amount FLOAT64,
               is_fraud BOOL, V1..V28 FLOAT64 PCA features)

Edge table:
  CardPerformedTransaction  KEY (card_id, transaction_id)
    SOURCE       Card         via card_id
    DESTINATION  Transaction  via transaction_id
    LABEL        PERFORMED
    PROPERTIES   (time_seconds, amount, is_fraud)

The property graph is `{PROJECT_ID}.{DATASET_ID}.FraudGraph`.

BigQuery GQL is accessed via the GRAPH_TABLE table function. Example:

  SELECT card_id, fraud_count, total_count
  FROM GRAPH_TABLE (
    {PROJECT_ID}.{DATASET_ID}.FraudGraph
    MATCH (c:Card)-[e:PERFORMED]->(t:Transaction)
    RETURN c.card_id AS card_id,
           COUNTIF(t.is_fraud) AS fraud_count,
           COUNT(*) AS total_count
    GROUP BY card_id
  )
  ORDER BY fraud_count DESC
  LIMIT 10;

Useful aggregate columns on Transaction:
  - is_fraud is a BOOL; COUNTIF(is_fraud) gives fraud counts.
  - time_seconds is a FLOAT64 offset (seconds since dataset start).
  - amount is the transaction amount in the dataset's currency.

When an analytical question does not need graph traversal, query the
tables directly with plain SQL. Use GRAPH_TABLE only for multi-hop or
pattern-based questions.
""".strip()


def _coerce_cell(value: Any) -> Any:
    """Make BigQuery row values JSON-serialisable."""
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _run_query(sql: str, row_limit: int) -> list[dict]:
    effective_limit = max(1, min(row_limit, HARD_ROW_LIMIT))
    job_config = bigquery.QueryJobConfig(
        use_query_cache=True,
        maximum_bytes_billed=MAX_BYTES_BILLED,
    )
    logger.info("Executing BQ SQL (limit=%d): %s", effective_limit, sql.replace("\n", " \\ "))
    query_job = bq_client.query(sql, job_config=job_config, location="US")
    rows = query_job.result(max_results=effective_limit)
    schema = rows.schema
    out: list[dict] = []
    for row in rows:
        out.append({field.name: _coerce_cell(row[field.name]) for field in schema})
    return out


mcp = FastMCP(
    name="analytical-graph-shim",
    instructions=(
        "Warehouse-scale analytical tools over the BigQuery FraudGraph "
        "property graph and the underlying Card and Transaction tables. "
        "Use describe_schema first if unsure about structure, then run_sql "
        "to execute queries (plain SQL or GRAPH_TABLE-wrapped GQL)."
    ),
    stateless_http=True,
    json_response=True,
)


@mcp.tool()
def describe_schema() -> str:
    """Return the FraudGraph schema, available columns, and a GRAPH_TABLE example.

    Call this first if you are unsure how to phrase a query. Returns the
    authoritative schema, cost-safe usage notes, and a working GRAPH_TABLE
    example that you can adapt.
    """
    return FRAUDGRAPH_SCHEMA_HINT


@mcp.tool()
def run_sql(sql: str, row_limit: int = DEFAULT_ROW_LIMIT) -> list[dict]:
    """Execute a read-only BigQuery SQL statement and return rows.

    Accepts either plain SQL against the graph_intel_metadata tables or a
    SELECT that wraps a GRAPH_TABLE(...) expression for GQL-style graph
    traversals over FraudGraph.

    Parameters:
      sql         - BigQuery GoogleSQL. Must be SELECT-only; DDL and DML
                    are rejected by the shim. Prefer qualified names like
                    `neo4jeventdemos.graph_intel_metadata.Transaction`.
      row_limit   - Maximum rows to return (default 100, hard cap 1000).
                    Billing is per bytes scanned, not rows, so prefer
                    aggregations and WHERE filters to control cost.

    Guardrails:
      - Queries are billed against a service account budget and are capped
        at approximately 1 GiB of bytes scanned. Narrow SELECT lists and
        filter aggressively.
      - On syntax or schema errors the tool raises ValueError with the
        BigQuery error text plus the FraudGraph schema so you can retry.
    """
    stripped = sql.lstrip().upper()
    if not stripped.startswith(("SELECT", "WITH")):
        raise ValueError(
            "Only SELECT/WITH statements are allowed on the analytical shim. "
            "For DDL or DML, use a separate administrative path."
        )
    try:
        return _run_query(sql, row_limit)
    except Exception as exc:
        logger.warning("BQ query failed: %s", exc)
        raise ValueError(
            f"BigQuery error: {exc}. Revise the query using this reference:\n{FRAUDGRAPH_SCHEMA_HINT}"
        ) from exc


# ---------------------------------------------------------------------------
# REST surface for human debugging (curl, browser). Not used by the agent.
# ---------------------------------------------------------------------------

rest = FastAPI(title="BigQuery Analytical Shim (REST)")


class SQLRequest(BaseModel):
    sql: str
    row_limit: Optional[int] = DEFAULT_ROW_LIMIT


@rest.get("/health")
def health() -> dict:
    return {"status": "healthy", "project": PROJECT_ID, "dataset": DATASET_ID}


@rest.get("/schema")
def rest_schema() -> dict:
    return {"schema": FRAUDGRAPH_SCHEMA_HINT}


@rest.post("/query")
def rest_query(request: SQLRequest) -> dict:
    try:
        return {"rows": run_sql(request.sql, request.row_limit or DEFAULT_ROW_LIMIT)}
    except ValueError as exc:
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
