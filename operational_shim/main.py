import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from google.cloud import spanner
from typing import List, Optional

app = FastAPI(title="Spanner Graph Operational Shim")

# Environment Variables
INSTANCE_ID = os.getenv("SPANNER_INSTANCE_ID", "spanner-graph-instance")
DATABASE_ID = os.getenv("SPANNER_DATABASE_ID", "spanner-graph-db")

# Spanner Client Setup
client = spanner.Client()
instance = client.instance(INSTANCE_ID)
database = instance.database(DATABASE_ID)

class GQLRequest(BaseModel):
    gql: str
    params: Optional[dict] = None

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/account/{account_id}")
def get_account(account_id: int):
    """Retrieves account details using a point-lookup GQL query."""
    gql = """
    GRAPH FinGraph
    MATCH (a:Account {id: @account_id})
    RETURN a.id, a.is_active, a.account_type
    """
    params = {"account_id": account_id}
    param_types = {"account_id": spanner.param_types.INT64}
    
    with database.snapshot() as snapshot:
        results = snapshot.execute_sql(gql, params=params, param_types=param_types)
        rows = list(results)
        if not rows:
            raise HTTPException(status_code=404, detail="Account not found")
        
        row = rows[0]
        return {"id": row[0], "is_active": row[1], "account_type": row[2]}

@app.post("/query")
def execute_gql(request: GQLRequest):
    """Executes an arbitrary GQL query (for use by the Agent)."""
    try:
        with database.snapshot() as snapshot:
            results = snapshot.execute_sql(request.gql, params=request.params)
            return {"results": list(results)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/person/{person_id}/network")
def get_person_network(person_id: int):
    """Finds immediate network (accounts owned) using GQL traversal."""
    gql = """
    GRAPH FinGraph
    MATCH (p:Person {id: @person_id})-[:Owns]->(a:Account)
    RETURN p.name, a.id, a.is_active
    """
    params = {"person_id": person_id}
    param_types = {"person_id": spanner.param_types.INT64}
    
    with database.snapshot() as snapshot:
        results = snapshot.execute_sql(gql, params=params, param_types=param_types)
        return {"network": list(results)}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
