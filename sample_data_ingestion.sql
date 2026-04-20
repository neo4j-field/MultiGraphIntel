-- SEEDING SAMPLE DATA FOR GRAPH INTELLIGENCE (Spanner FinGraph)

-- Insert Persons
INSERT INTO Person (id, name, country) VALUES
(1, 'Alice', 'USA'),
(2, 'Bob', 'UK'),
(3, 'Charlie', 'USA'),
(4, 'Dana', 'Canada');

-- Insert Accounts
INSERT INTO Account (id, create_time, is_active, account_type) VALUES
(101, CURRENT_TIMESTAMP(), true, 'Checking'),
(102, CURRENT_TIMESTAMP(), true, 'Savings'),
(103, CURRENT_TIMESTAMP(), true, 'Checking'),
(104, CURRENT_TIMESTAMP(), false, 'Business');

-- Ownership
INSERT INTO PersonOwnAccount (person_id, account_id) VALUES
(1, 101), (2, 102), (3, 103), (4, 104);

-- Circular Transfer (Money Laundering Pattern)
INSERT INTO AccountTransferAccount (from_id, to_id, amount, create_time, transaction_id, transaction_type) VALUES
(101, 102, 1200.0, CURRENT_TIMESTAMP(), 'TXN-0001', 'WIRE'),
(102, 103, 1200.0, CURRENT_TIMESTAMP(), 'TXN-0002', 'WIRE'),
(103, 101, 1200.0, CURRENT_TIMESTAMP(), 'TXN-0003', 'WIRE');

-- Fan-out Pattern (Suspicious Activity)
INSERT INTO AccountTransferAccount (from_id, to_id, amount, create_time, transaction_id, transaction_type) VALUES
(101, 103, 50.0, CURRENT_TIMESTAMP(), 'TXN-0004', 'P2P'),
(101, 104, 50.0, CURRENT_TIMESTAMP(), 'TXN-0005', 'P2P');
