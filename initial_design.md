# Multi-Agent Graph Intelligence Architecture on GCP

## Overview

This document captures the architectural foundation for a multi-agent system deployed on **Vertex AI Agent Builder**. The system is designed to route graph intelligence queries across three specialized data substrates on Google Cloud Platform, using a **Coordinator-Dispatcher** pattern.

## Core Architecture

The root agent, `graph-intelligence-router`, serves as the primary entry point for user interaction. It analyzes the user's intent and delegates the query to one of three specialized subagents using the `transfer_to_agent` mechanism.

### 1. Root Router: `graph-intelligence-router`
- **Model:** Gemini 3 Pro
- **Role:** Intent analysis, delegation, and result synthesis.
- **Protocol:** A2A v1.0 Peer (Agent-to-Agent).

### 2. Analytical Subagent: `analytical_graph_agent`
- **Data Substrate:** BigQuery Graph
- **Specialization:** Warehouse-scale queries, historical pattern matching, and long-tail aggregations.
- **Key Capabilities:** NL-to-GQL via Conversational Analytics, AI.FORECAST, and AI.DETECT_ANOMALIES.

### 3. Operational Subagent: `operational_graph_agent`
- **Data Substrate:** Spanner Graph
- **Specialization:** Low-latency, transactional graph queries, and real-time entity lookups.
- **Key Capabilities:** High-concurrency GQL execution via a Cloud Run shim or direct Spanner client.

### 4. Intelligence Subagent: `intelligence_graph_agent`
- **Data Substrate:** Neo4j Aura on GCP + GDS
- **Specialization:** Complex reasoning, community detection, memory preservation, and link prediction.
- **Key Capabilities:** Integrated MCP servers for Cypher, Memory, and Data Modeling.

## Data Enrichment Loop

To ensure a unified graph intelligence layer, the architecture includes a data feedback loop:
1.  **Ingestion:** Raw transactional data in BigQuery is modeled as a Property Graph.
2.  **Enrichment:** Dataflow pipelines migrate relevant subsets to Neo4j Aura for advanced algorithmic analysis (e.g., PageRank, Louvain).
3.  **Reverse ETL:** Enriched scores and community IDs are written back to BigQuery, surfacing as high-value BI columns for the analytical agent.

## Security & IAM

- **Identity:** All agents operate under a dedicated service account (e.g., `graph-intel-sa@<PROJECT_ID>.iam.gserviceaccount.com`).
- **Least Privilege:**
    - `roles/bigquery.jobUser` and `roles/bigquery.dataViewer` for analytical workloads.
    - `roles/spanner.databaseUser` for operational workloads.
    - Secret Manager access for Neo4j Aura credentials.
    - `roles/aiplatform.user` for Vertex AI Agent Engine execution.

## Architectural Trade-offs

| Factor | Analytical (BQ) | Operational (Spanner) | Intelligence (Neo4j) |
| :--- | :--- | :--- | :--- |
| **Latency** | Higher (Batch/Warehouse) | Low (Transactional) | Moderate (Reasoning/Algo) |
| **Scale** | Petabyte-scale | Horizontal (Global) | High (Memory/GDS) |
| **Query Language** | GQL over SQL tables | Native GQL | Cypher / MCP |
| **Primary Use Case** | Historical Patterns | Live Transactions | Reasoning & Memory |

## Tooling Strategy

- **MCP (Model Context Protocol):** Used exclusively for the `intelligence_graph_agent` to expose deep graph operations and memory state to the LLM.
- **Vertex AI Agent Engine:** Provides the runtime for agent deployment and A2A communication.
- **Secret Manager:** Ensures secure management of Aura connection strings and API keys.
