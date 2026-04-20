-- Spanner Graph DDL for operational_graph_agent
-- This maps the FinGraph model for high-concurrency, low-latency operational queries.

-- 1. Create Tables (Relational Layer)
CREATE TABLE Person (
  id INT64 NOT NULL,
  name STRING(MAX),
  country STRING(MAX),
) PRIMARY KEY (id);

CREATE TABLE Account (
  id INT64 NOT NULL,
  create_time TIMESTAMP,
  is_active BOOL,
  account_type STRING(MAX),
) PRIMARY KEY (id);

CREATE TABLE PersonOwnAccount (
  person_id INT64 NOT NULL,
  account_id INT64 NOT NULL,
  CONSTRAINT FK_Person FOREIGN KEY (person_id) REFERENCES Person(id),
  CONSTRAINT FK_Account FOREIGN KEY (account_id) REFERENCES Account(id),
) PRIMARY KEY (person_id, account_id);

CREATE TABLE AccountTransferAccount (
  from_id INT64 NOT NULL,
  to_id INT64 NOT NULL,
  amount FLOAT64,
  create_time TIMESTAMP NOT NULL,
  transaction_id STRING(MAX) NOT NULL,
  transaction_type STRING(MAX),
  CONSTRAINT FK_FromAccount FOREIGN KEY (from_id) REFERENCES Account(id),
  CONSTRAINT FK_ToAccount FOREIGN KEY (to_id) REFERENCES Account(id),
) PRIMARY KEY (from_id, to_id, create_time, transaction_id);

-- 2. Define the Property Graph
CREATE PROPERTY GRAPH FinGraph
NODE TABLES (
  Person KEY (id) LABEL Person,
  Account KEY (id) LABEL Account
)
EDGE TABLES (
  PersonOwnAccount
    SOURCE KEY (person_id) REFERENCES Person (id)
    DESTINATION KEY (account_id) REFERENCES Account (id)
    LABEL Owns,
  AccountTransferAccount
    SOURCE KEY (from_id) REFERENCES Account (id)
    DESTINATION KEY (to_id) REFERENCES Account (id)
    LABEL Transfers
);
