-- FraudGraph bipartite property graph over the public ULB fraud dataset.
--
-- The public dataset has no stable row key and no cardholder dimension, so a
-- meaningful graph cannot be defined directly on top of it. This script
-- materializes a compact demo dataset inside `graph_intel_metadata`:
--   1. Transaction  - snapshot of the public rows with a stable transaction_id
--   2. Card         - 500 synthetic cards
--   3. CardPerformedTransaction  - bipartite edges, fraud-biased card assignment
--   4. FraudGraph   - property graph over Card and Transaction
--
-- Cost note: snapshots ~150MB of public data once. Subsequent queries read
-- only from the local tables under graph_intel_metadata.

-- 1. Dataset
CREATE SCHEMA IF NOT EXISTS `neo4jeventdemos.graph_intel_metadata`
OPTIONS (location = 'US');

-- 2. Snapshot the public ULB fraud transactions with a stable UUID key.
CREATE OR REPLACE TABLE `neo4jeventdemos.graph_intel_metadata.Transaction` AS
SELECT
  GENERATE_UUID() AS transaction_id,
  Time           AS time_seconds,
  Amount         AS amount,
  CAST(Class AS BOOL) AS is_fraud,
  V1,  V2,  V3,  V4,  V5,  V6,  V7,  V8,  V9,  V10,
  V11, V12, V13, V14, V15, V16, V17, V18, V19, V20,
  V21, V22, V23, V24, V25, V26, V27, V28
FROM `bigquery-public-data.ml_datasets.ulb_fraud_detection`;

-- 3. Synthetic Card dimension (500 cards across four countries and three networks).
CREATE OR REPLACE TABLE `neo4jeventdemos.graph_intel_metadata.Card` AS
WITH card_series AS (
  SELECT n FROM UNNEST(GENERATE_ARRAY(1, 500)) AS n
)
SELECT
  CONCAT('CARD-', LPAD(CAST(n AS STRING), 5, '0')) AS card_id,
  CASE MOD(n, 3)
    WHEN 0 THEN 'VISA'
    WHEN 1 THEN 'MASTERCARD'
    ELSE        'AMEX'
  END AS card_type,
  CASE MOD(n, 4)
    WHEN 0 THEN 'USA'
    WHEN 1 THEN 'UK'
    WHEN 2 THEN 'CANADA'
    ELSE        'GERMANY'
  END AS country,
  CONCAT('Issuer-', CAST(MOD(n, 10) AS STRING)) AS issuer
FROM card_series;

-- 4. Bipartite edge table.
--    Fraud transactions are biased into the first 50 cards so demo queries
--    surface meaningful rings. Legit transactions spread across all 500.
CREATE OR REPLACE TABLE `neo4jeventdemos.graph_intel_metadata.CardPerformedTransaction` AS
SELECT
  CASE
    WHEN is_fraud THEN
      CONCAT('CARD-', LPAD(CAST(1 + MOD(ABS(FARM_FINGERPRINT(transaction_id)), 50) AS STRING), 5, '0'))
    ELSE
      CONCAT('CARD-', LPAD(CAST(1 + MOD(ABS(FARM_FINGERPRINT(transaction_id)), 500) AS STRING), 5, '0'))
  END AS card_id,
  transaction_id,
  time_seconds,
  amount,
  is_fraud
FROM `neo4jeventdemos.graph_intel_metadata.Transaction`;

-- 5. Property graph definition over the bipartite model.
--    BigQuery requires table aliases when edge REFERENCES clauses point at
--    node tables, and edge tables need an explicit KEY declaration.
CREATE OR REPLACE PROPERTY GRAPH `neo4jeventdemos.graph_intel_metadata.FraudGraph`
NODE TABLES (
  `neo4jeventdemos.graph_intel_metadata.Card` AS Card
    KEY (card_id)
    LABEL Card
    PROPERTIES (card_id, card_type, country, issuer),
  `neo4jeventdemos.graph_intel_metadata.Transaction` AS Transaction
    KEY (transaction_id)
    LABEL Transaction
    PROPERTIES (transaction_id, time_seconds, amount, is_fraud)
)
EDGE TABLES (
  `neo4jeventdemos.graph_intel_metadata.CardPerformedTransaction` AS CardPerformed
    KEY (card_id, transaction_id)
    SOURCE KEY      (card_id)        REFERENCES Card (card_id)
    DESTINATION KEY (transaction_id) REFERENCES Transaction (transaction_id)
    LABEL PERFORMED
    PROPERTIES (time_seconds, amount, is_fraud)
);
