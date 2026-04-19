-- GRAPH DEFINITION FOR PUBLIC DATASET: ulb_fraud_detection
-- Note: This creates a virtual graph layer over the existing public BigQuery tables.

-- Step 1: Create a local dataset to hold our graph metadata
CREATE SCHEMA IF NOT EXISTS graph_intel_metadata;

-- Step 2: Define the Property Graph
-- We model Transactions as Edges between Card identifiers.
-- Since the public dataset is anonymized (V1-V28 features), 
-- we use the 'Time' and 'Amount' as key properties.

CREATE OR REPLACE PROPERTY GRAPH graph_intel_metadata.FraudGraph
NODE TABLES (
  -- We treat each unique transaction as a node for this specific logic
  `bigquery-public-data.ml_datasets.ulb_fraud_detection` 
    KEY (Time, Amount) 
    LABEL TransactionNode
)
EDGE TABLES (
  -- In a real scenario, we'd have a 'Card' table to join. 
  -- For this demo, we can model self-relationships or temporal sequences.
  `bigquery-public-data.ml_datasets.ulb_fraud_detection`
    SOURCE KEY (Time, Amount) REFERENCES TransactionNode (Time, Amount)
    DESTINATION KEY (Time, Amount) REFERENCES TransactionNode (Time, Amount)
    LABEL TEMPORAL_SEQUENCE
);

/* 
ARCHITECTURAL NOTE: 
In a production environment, we would typically join this public 
transaction table with a private 'Customer' or 'Card' node table 
to create a true bipartite graph: (Card)-[:PERFORMED]->(Transaction).
*/
