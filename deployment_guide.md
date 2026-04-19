# Deployment Guide: Graph Intelligence Multi-Agent System

This guide outlines the manual steps and final configuration required to deploy the Graph Intelligence Multi-Agent System on GCP.

## Prerequisites

1.  **GCP Project:** Set your target project ID in your environment.
2.  **Terraform:** Apply the configuration in `infra/` to enable APIs and create the service account.
    ```bash
    cd infra
    terraform init
    terraform apply
    ```
3.  **Neo4j Aura:** Ensure an Aura instance is running and credentials are stored in GCP Secret Manager.

## Step 1: Vertex AI Agent Builder Configuration

### 1.1 Root Router (`graph-intelligence-router`)
- **Model:** Gemini 3 Pro
- **System Instruction:** Use the instruction from `prompts/prompts.md`.
- **Tools:** Enable `transfer_to_agent`.

### 1.2 Analytical Subagent (`analytical_graph_agent`)
- **Model:** Gemini 3 Flash
- **System Instruction:** Use the instruction from `subagent_instructions.md`.
- **Tools:** Configure the BigQuery Conversational Analytics tool.

### 1.3 Operational Subagent (`operational_graph_agent`)
- **Model:** Gemini 3 Flash
- **System Instruction:** Use the instruction from `subagent_instructions.md`.
- **Tools:** Deploy the Cloud Run shim for GQL and configure it as an Agent tool.

### 1.4 Intelligence Subagent (`intelligence_graph_agent`)
- **Model:** Gemini 3.1 Pro (Deep Think optional)
- **System Instruction:** Use the instruction from `subagent_instructions.md`.
- **Tools:** Configure the Neo4j MCP servers (Cypher, Memory, etc.).

## Step 2: Agent Designer Canvas

1.  Open the Vertex AI Agent Builder console.
2.  Create the `graph-intelligence-router`.
3.  Add the three subagents as nodes in the canvas.
4.  Connect the root router to each subagent via the `transfer_to_agent` mechanism.

## Step 3: Service Account Attachment

Ensure the `graph-intel-sa` service account is attached to the Vertex AI Agent Engine runtime to allow the agents to access BigQuery, Spanner, and Secret Manager.

## Step 4: Data Enrichment Pipeline

Deploy the Dataflow job to migrate and enrich data between BigQuery and Neo4j Aura, as described in the `initial_design.md`.
