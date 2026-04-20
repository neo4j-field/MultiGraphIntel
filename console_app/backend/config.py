"""Environment-driven configuration for the console backend."""
import os

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "neo4jeventdemos")
LOCATION = os.getenv("GCP_LOCATION", "us-central1")

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")

MCP_OPERATIONAL_URL = os.getenv(
    "MCP_OPERATIONAL_URL",
    "https://operational-graph-shim-276655847704.us-central1.run.app/mcp/",
)
MCP_ANALYTICAL_URL = os.getenv(
    "MCP_ANALYTICAL_URL",
    "https://analytical-graph-shim-276655847704.us-central1.run.app/mcp/",
)
MCP_INTELLIGENCE_URL = os.getenv(
    "MCP_INTELLIGENCE_URL",
    "https://intelligence-graph-shim-276655847704.us-central1.run.app/mcp/",
)

# Direct Neo4j driver (separate from the agent) powers the subgraph endpoint
# so NVL renders the "what you're reading about" subgraph in real time.
NEO4J_URI = os.environ.get("NEO4J_URI")
NEO4J_USERNAME = os.environ.get("NEO4J_USERNAME")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

MAX_AGENT_ITERATIONS = int(os.getenv("MAX_AGENT_ITERATIONS", "10"))
