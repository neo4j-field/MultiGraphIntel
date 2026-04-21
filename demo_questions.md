# Sample Questions for the Graph Intelligence Router

These prompts are validated against the deployed multi-agent system. Ask
them in **Vertex AI Studio → Agents → Preview** on the `graph-intelligence-router` canvas. No "using X agent" prefix is needed. The router analyses intent and delegates automatically.

Each question is tagged with:
- the substrate it routes to,
- the tool the agent will call, and
- the expected shape of the answer.

> [Screenshot placeholder: docs/images/router-canvas.png - Agent canvas showing the router and three subagents]

---

## 1. Operational Graph Agent (Spanner FinGraph)

For **live, low-latency** account and transfer questions. Strength: sub-second transactional lookups.

### 1.1 Point lookup on account status
> Is account 101 currently active?

- Tool: `operational.get_account`
- Expected: "Yes, account 101 is currently active (Checking). Cited from Spanner FinGraph."

### 1.2 One-hop ownership
> Which accounts does person 1 own right now?

- Tool: `operational.get_person_network`
- Expected: Alice owns account 101, active Checking.

### 1.3 Direct transfer outflow
> Show me every direct transfer leaving account 101 with amounts and types.

- Tool: `operational.execute_gql`
- Expected: three rows, 101 to 102 at 1200 WIRE, 101 to 103 at 50 P2P, 101 to 104 at 50 P2P.

### 1.4 Ring detection via GQL
> Is there a circular transfer chain from account 101 through two other accounts and back to 101?

- Tool: `operational.execute_gql`
- Expected: three-hop ring found: 101 to 102 to 103 to 101, each hop at 1200 WIRE.

---

## 2. Analytical Graph Agent (BigQuery FraudGraph)

For **warehouse-scale historical** questions, fraud aggregates, and pattern analytics. Strength: petabyte-grade scanning with AI/ML functions built in.

### 2.1 Schema discovery
> Describe the BigQuery FraudGraph schema.

- Tool: `analytical.describe_schema`
- Expected: FraudGraph schema with Card, Transaction, and PERFORMED edges.

### 2.2 Top fraud cards
> Which five cards have the highest fraud counts, and what are their fraud rates?

- Tool: `analytical.run_sql` (wrapping a `GRAPH_TABLE` call)
- Expected:

| card_id    | fraud_count | total_count |
|-----------:|:-----------:|:-----------:|
| CARD-00050 | 17          | 592         |
| CARD-00013 | 14          | 574         |
| CARD-00008 | 14          | 576         |
| CARD-00035 | 14          | 594         |
| CARD-00005 | 13          | 591         |

### 2.3 Fraud vs legit average amount
> What is the average transaction amount for fraud vs non-fraud transactions in the dataset?

- Tool: `analytical.run_sql`
- Expected: aggregate over 284,807 rows from the ULB public dataset.

---

## 3. Intelligence Graph Agent (Neo4j Aura + GDS)

For **reasoning, graph algorithms, and analyst memory**. These four questions were chosen specifically because neither Spanner nor BigQuery can answer them convincingly.

> [Screenshot placeholder: docs/images/intelligence-agent-preview.png - Vertex AI Preview pane showing an Intelligence answer with substrate citation]

### 3.1 Entity 360 briefing
> Give me a complete intelligence briefing on account 101: who owns it, what community it is in, any rings or cases it is involved in, linked cards, and our risk assessment.

- Tool: `intelligence.run_cypher` (single OPTIONAL MATCH query)
- Expected in one response:
  - Owner: **Alice**
  - Community: **7**, PageRank `0.048`, fraud_score `0.91`
  - Case: **CASE-2026-04-15** opened by **Sarah Chen**, recommends filing an SAR, freezing outbound transfers, and escalating to compliance
  - Ring path: **101 → 102 → 103 → 101**
  - Linked cards: **CARD-00050**
  - Community peers: 102 and 103

Why only Neo4j can answer this: `community_id`, `pagerank_score`, `fraud_score`, `Case` nodes, analyst memory, `SUSPECTED_LAUNDERING_RING` edges, and the `LINKED_TO_CARD` bridge to BigQuery's FraudGraph all live only in Neo4j. Spanner has the raw live data but no enrichment. BigQuery has fraud aggregates but no Person or Case concept.

### 3.2 Graph algorithms via GDS
> Run PageRank on the account transfer network in Neo4j and tell me which account has the highest influence.

- Tool: `intelligence.run_cypher` (`gds.graph.project` then `gds.pageRank.stream`, then `gds.graph.drop`)
- Expected:

| account_id | pagerank |
|-----------:|---------:|
| 101        | 0.695    |
| 103        | 0.641    |
| 102        | 0.347    |
| 104        | 0.347    |

Why only Neo4j can answer this: Graph Data Science algorithms (PageRank, Louvain, WCC, Node2Vec, link prediction) run natively on Neo4j. Spanner and BigQuery have no comparable production graph algorithm suite invocable through an agent tool.

### 3.3 Ring financial impact
> What is the total money moving through the suspected laundering ring, and which accounts are involved?

- Tool: `intelligence.run_cypher`
- Expected: `RING-001` covers 101 → 102 → 103 → 101, with **$3,650 total across 4 transfers**.

Why only Neo4j can answer this: `SUSPECTED_LAUNDERING_RING` is pre-computed and annotated only in Neo4j. Blending ring topology with transfer amounts is idiomatic graph-native reasoning.

### 3.4 Cross-substrate risk narrative
> Which of our people transact with cards that BigQuery flagged as high-fraud, and is there an open investigation case for them?

- Tool: `intelligence.run_cypher`
- Expected:
  - **Alice** owns account 101 (fraud_score 0.91), linked to **CARD-00050** (17 BigQuery frauds, AMEX/USA), case **CASE-2026-04-15**.
  - **Bob** owns account 102 (fraud_score 0.87), linked to **CARD-00013** (14 BigQuery frauds, VISA/UK), case **CASE-2026-04-15**.

Why only Neo4j can answer this: the `LINKED_TO_CARD` relationship is the bridge back to BigQuery's FraudGraph. Only Neo4j holds this link, which is the "unified graph intelligence" story the initial design calls out.

### 3.5 Open in Bloom for visual exploration
> Open account 101 in Neo4j Bloom so I can explore the ring visually.

- Tool: `intelligence.bloom_deeplink`
- Expected: the agent replies with
  - a Workspace Explore URL pre-wired to the Aura 27ad415a instance,
  - the suggested search phrase **`Account 101`** to paste into the Explore search bar,
  - and a one-line instruction to sign in to Aura and run the search.

Why only Neo4j can answer this: Bloom (now Workspace Explore) is a Neo4j-native graph discovery tool. Spanner and BigQuery have nothing equivalent. The Router hands the user off to a tool designed for human-led visual forensics, keeping the chat answer clickable rather than trying to render the graph in the chat UI.

> [Screenshot placeholder: docs/images/bloom-explore-account-101.png - Workspace Explore view after pasting the suggested search phrase]

---

## A note on data density

Questions 3.1 through 3.4 work today against the existing seed.

Louvain and Weakly Connected Components (WCC) will run but are visually underwhelming on our current four-account graph because all accounts form a single dense cluster. If you want those algorithms to shine as a demo, extend `neo4j_load.cypher` with 30-40 accounts across disjoint structures (two more rings, a hub-and-spoke, and a pair of isolated accounts). The `intelligence_shim` already permits the required GDS procedures.
