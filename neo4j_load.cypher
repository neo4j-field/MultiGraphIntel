// -----------------------------------------------------------------------------
// Neo4j Intelligence Graph load script for the MultiGraphIntel demo.
//
// Idempotent: all writes use MERGE so the script can be re-run safely. If
// Person or Account nodes with the same ids already exist, their properties
// are updated in place.
//
// Model:
//   - Mirrors the Spanner FinGraph Person/Account/OWNS/TRANSFERS structure
//     so a single user question can cite either substrate.
//   - Adds Neo4j-only enrichments that the Intelligence Agent should surface:
//       * community_id, pagerank_score, fraud_score on Account
//       * SUSPECTED_LAUNDERING_RING edges over the 101-102-103 ring
//       * Case node with analyst memory (the "memory" capability of the agent)
//       * Card nodes + LINKED_TO_CARD edges bridging to the BigQuery FraudGraph
// -----------------------------------------------------------------------------

// 1. Constraints - executed individually because CREATE CONSTRAINT cannot be
//    composed with other statements in a single Cypher block.
CREATE CONSTRAINT person_id IF NOT EXISTS FOR (p:Person) REQUIRE p.id IS UNIQUE;
CREATE CONSTRAINT account_id IF NOT EXISTS FOR (a:Account) REQUIRE a.id IS UNIQUE;
CREATE CONSTRAINT card_id IF NOT EXISTS FOR (c:Card) REQUIRE c.card_id IS UNIQUE;
CREATE CONSTRAINT case_id IF NOT EXISTS FOR (k:Case) REQUIRE k.case_id IS UNIQUE;

// 2. Persons - identical to Spanner FinGraph.
MERGE (alice:Person   {id: 1}) SET alice.name   = 'Alice',   alice.country   = 'USA';
MERGE (bob:Person     {id: 2}) SET bob.name     = 'Bob',     bob.country     = 'UK';
MERGE (charlie:Person {id: 3}) SET charlie.name = 'Charlie', charlie.country = 'USA';
MERGE (dana:Person    {id: 4}) SET dana.name    = 'Dana',    dana.country    = 'Canada';

// 3. Accounts - same ids as Spanner, plus Neo4j-only enrichments.
//    community_id, pagerank_score and fraud_score are values an analyst
//    would get from GDS (Louvain, PageRank) or a scoring pipeline. For the
//    demo they are hand-set to reflect the ring we seeded.
MERGE (a101:Account {id: 101})
  SET a101.is_active = true,
      a101.account_type = 'Checking',
      a101.community_id = 7,
      a101.pagerank_score = 0.048,
      a101.fraud_score = 0.91;

MERGE (a102:Account {id: 102})
  SET a102.is_active = true,
      a102.account_type = 'Savings',
      a102.community_id = 7,
      a102.pagerank_score = 0.042,
      a102.fraud_score = 0.87;

MERGE (a103:Account {id: 103})
  SET a103.is_active = true,
      a103.account_type = 'Checking',
      a103.community_id = 7,
      a103.pagerank_score = 0.040,
      a103.fraud_score = 0.82;

MERGE (a104:Account {id: 104})
  SET a104.is_active = false,
      a104.account_type = 'Business',
      a104.community_id = 12,
      a104.pagerank_score = 0.012,
      a104.fraud_score = 0.34;

// 4. Ownership edges - mirrors Spanner PersonOwnAccount.
MATCH (p:Person {id: 1}), (a:Account {id: 101}) MERGE (p)-[:OWNS]->(a);
MATCH (p:Person {id: 2}), (a:Account {id: 102}) MERGE (p)-[:OWNS]->(a);
MATCH (p:Person {id: 3}), (a:Account {id: 103}) MERGE (p)-[:OWNS]->(a);
MATCH (p:Person {id: 4}), (a:Account {id: 104}) MERGE (p)-[:OWNS]->(a);

// 5. Transfers - same five rows as Spanner AccountTransferAccount.
MATCH (a:Account {id: 101}), (b:Account {id: 102})
MERGE (a)-[t:TRANSFERS {transaction_id: 'TXN-0001'}]->(b)
  SET t.amount = 1200.0, t.transaction_type = 'WIRE', t.at = datetime();

MATCH (a:Account {id: 102}), (b:Account {id: 103})
MERGE (a)-[t:TRANSFERS {transaction_id: 'TXN-0002'}]->(b)
  SET t.amount = 1200.0, t.transaction_type = 'WIRE', t.at = datetime();

MATCH (a:Account {id: 103}), (b:Account {id: 101})
MERGE (a)-[t:TRANSFERS {transaction_id: 'TXN-0003'}]->(b)
  SET t.amount = 1200.0, t.transaction_type = 'WIRE', t.at = datetime();

MATCH (a:Account {id: 101}), (b:Account {id: 103})
MERGE (a)-[t:TRANSFERS {transaction_id: 'TXN-0004'}]->(b)
  SET t.amount = 50.0, t.transaction_type = 'P2P', t.at = datetime();

MATCH (a:Account {id: 101}), (b:Account {id: 104})
MERGE (a)-[t:TRANSFERS {transaction_id: 'TXN-0005'}]->(b)
  SET t.amount = 50.0, t.transaction_type = 'P2P', t.at = datetime();

// 6. Neo4j-only enrichment: SUSPECTED_LAUNDERING_RING over the circular wire.
MATCH (a:Account {id: 101}), (b:Account {id: 102})
MERGE (a)-[:SUSPECTED_LAUNDERING_RING {ring_id: 'RING-001'}]->(b);
MATCH (a:Account {id: 102}), (b:Account {id: 103})
MERGE (a)-[:SUSPECTED_LAUNDERING_RING {ring_id: 'RING-001'}]->(b);
MATCH (a:Account {id: 103}), (b:Account {id: 101})
MERGE (a)-[:SUSPECTED_LAUNDERING_RING {ring_id: 'RING-001'}]->(b);

// 7. Case node - the "memory" layer. This is what an analyst wrote when they
//    last reviewed this ring. The Intelligence Agent should surface it when
//    asked about suspicious activity touching accounts 101, 102, or 103.
MERGE (c:Case {case_id: 'CASE-2026-04-15'})
  SET c.opened_at = datetime('2026-04-15T14:30:00'),
      c.status = 'OPEN',
      c.analyst = 'Sarah Chen',
      c.summary = 'Three-account wire ring moving 1200 USD between accounts 101, 102, 103.',
      c.recommended_action = 'File SAR, freeze outbound transfers, escalate to compliance.';

MATCH (c:Case {case_id: 'CASE-2026-04-15'}),
      (a:Account) WHERE a.id IN [101, 102, 103]
MERGE (c)-[:INVESTIGATES]->(a);

// 8. Cross-substrate bridge: link two high-fraud Cards from BigQuery
//    FraudGraph back to Accounts in this graph. This enables the Intelligence
//    Agent to answer "which of our known accounts transacted with CARD-00050".
MERGE (card50:Card {card_id: 'CARD-00050'})
  SET card50.card_type = 'AMEX', card50.country = 'USA', card50.fraud_count = 17;
MERGE (card13:Card {card_id: 'CARD-00013'})
  SET card13.card_type = 'VISA', card13.country = 'UK',  card13.fraud_count = 14;

MATCH (c:Card {card_id: 'CARD-00050'}), (a:Account {id: 101})
MERGE (a)-[:LINKED_TO_CARD]->(c);
MATCH (c:Card {card_id: 'CARD-00013'}), (a:Account {id: 102})
MERGE (a)-[:LINKED_TO_CARD]->(c);
