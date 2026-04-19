# Multi-Agent System on GCP Vertex AI Agent Builder

Source: prior design conversation, captured verbatim.
Target platform: Vertex AI Agent Builder / ADK, Coordinator-Dispatcher pattern.
Deployment runtime: Vertex AI Agent Engine.
GCP project: <PROJECT_ID>, region us-central1.

Architecture: one root router delegates to three specialist subagents via
LLM-driven delegation (transfer_to_agent). Subagents own one data substrate
each: BigQuery Graph, Spanner Graph, and Neo4j Aura plus GDS.

================================================================================
ROOT AGENT: graph-intelligence-router
================================================================================

Model: Gemini 3.1 Pro
Role:  Coordinator / Dispatcher
Interop: A2A v1.0 peer, exposes standardized Agent Card

Description (agent card):
  Routes questions across operational, analytical, and intelligence graph
  workloads on Google Cloud.

System instruction:

  You are a graph intelligence router. For each user question:
  1. If the question is about historical patterns or aggregates across
     large datasets, delegate to the analytical_graph_agent.
  2. If the question is about a live entity, transaction, or session,
     delegate to the operational_graph_agent.
  3. If the question requires reasoning over relationships, memory of
     prior decisions, community membership, or link predictions,
     delegate to the intelligence_graph_agent (Neo4j Aura + GDS).
  Always cite which subagent answered and why.

================================================================================
SUBAGENT 1: analytical_graph_agent
================================================================================

Model: Gemini 3 Flash (proposed)
Data substrate: BigQuery Graph (Preview, Apr 14, 2026)
Entry tool:     Conversational Analytics in BigQuery
                NL-to-GQL, AI.FORECAST and AI.DETECT_ANOMALIES built in

Description (agent card):
  Historical, batch, warehouse-scale queries. Source: BigQuery Graph
  (Preview, Apr 14, 2026), property graphs over BQ tables. Entry tool:
  Conversational Analytics in BigQuery (NL-to-GQL with AI.FORECAST and
  AI.DETECT_ANOMALIES built in). Good at: 12-month fraud ring discovery,
  population-level patterns, long-tail aggregations.

System instruction:
  NOT YET AUTHORED in the prior conversation. To be drafted before
  deployment.

================================================================================
SUBAGENT 2: operational_graph_agent
================================================================================

Model: Gemini 3 Flash (proposed)
Data substrate: Spanner Graph (GA)
Entry tool:     GQL via Spanner client, or a Cloud Run shim

Description (agent card):
  Live, low-latency, transactional queries. Source: Spanner Graph (GA).
  Entry tool: GQL via Spanner client, or a Cloud Run shim. Good at:
  "is this specific account active now," "who did this session touch in
  the last 60 seconds".

System instruction:
  NOT YET AUTHORED in the prior conversation. To be drafted before
  deployment.

================================================================================
SUBAGENT 3: intelligence_graph_agent
================================================================================

Model: Gemini 3.1 Pro (proposed, upgradable to Deep Think for hard reasoning)
Data substrate: Neo4j Aura on GCP, with GDS and ingested unstructured data
                from LLM Knowledge Graph Builder
Entry tools:
  - mcp-neo4j-cypher
  - mcp-neo4j-memory
  - mcp-neo4j-data-modeling
  - mcp-neo4j-cloud-aura-api
  - Neo4j Aura Agent (REST endpoint, optional, hosted GraphRAG)

Description (agent card):
  Reasoning, memory, algorithms layer. Sources: Neo4j Aura on GCP with GDS
  and ingested unstructured data from LLM Knowledge Graph Builder. Entry
  tools: Neo4j MCP servers (mcp-neo4j-cypher, mcp-neo4j-memory,
  mcp-neo4j-data-modeling, mcp-neo4j-cloud-aura-api) and Neo4j Aura Agent
  via REST endpoint. Good at: "which community does this account belong to,"
  "predict the next hop even without a direct edge," "remember what the
  analyst decided last shift," "generate a narrative that cites the graph
  path".

System instruction:
  NOT YET AUTHORED in the prior conversation. To be drafted before
  deployment.

================================================================================
DATA LOOP (for reference)
================================================================================

  BigQuery Graph -> Dataflow -> Neo4j Aura -> GDS (PageRank, Louvain,
  link prediction) -> reverse-ETL back to BigQuery so enriched scores
  become BI columns usable by the analytical agent.

================================================================================
OPEN ITEMS
================================================================================

  1. Author full system instructions for the three subagents.
     The descriptions above are agent-card blurbs, not operating prompts.
  2. Add the three subagent nodes in Agent Designer canvas.
  3. Scaffold Terraform (infra/) to enable required APIs and create a
     dedicated service account with least-privilege IAM.
  4. Write initial_design.md capturing architecture decisions and
     trade-offs.
