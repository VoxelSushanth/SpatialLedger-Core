-- Store Intelligence System Database Schema
-- PostgreSQL 15

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Events table: stores all detection events
CREATE TABLE IF NOT EXISTS events (
  id           BIGSERIAL PRIMARY KEY,
  event_id     UUID NOT NULL UNIQUE,
  event_type   VARCHAR(20) NOT NULL,
  timestamp    TIMESTAMPTZ NOT NULL,
  person_id    VARCHAR(50) NOT NULL,
  person_type  VARCHAR(20) NOT NULL DEFAULT 'UNKNOWN',
  session_id   VARCHAR(50),
  zone_id      VARCHAR(30),
  camera_id    VARCHAR(20),
  confidence   FLOAT,
  re_entry     BOOLEAN DEFAULT FALSE,
  group_id     VARCHAR(50),
  metadata     JSONB,
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_events_timestamp ON events (timestamp);
CREATE INDEX idx_events_session ON events (session_id);
CREATE INDEX idx_events_type ON events (event_type);
CREATE INDEX idx_events_person ON events (person_id, timestamp);

-- Sessions table: tracks customer journey through store
CREATE TABLE IF NOT EXISTS sessions (
  id           BIGSERIAL PRIMARY KEY,
  session_id   VARCHAR(50) NOT NULL UNIQUE,
  person_id    VARCHAR(50) NOT NULL,
  person_type  VARCHAR(20) NOT NULL,
  state        VARCHAR(20) NOT NULL,
  started_at   TIMESTAMPTZ NOT NULL,
  ended_at     TIMESTAMPTZ,
  dwell_seconds INTEGER,
  zones_visited TEXT[],
  re_entry     BOOLEAN DEFAULT FALSE,
  group_id     VARCHAR(50),
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_sessions_state ON sessions (state);
CREATE INDEX idx_sessions_started ON sessions (started_at);
CREATE INDEX idx_sessions_person ON sessions (person_id);

-- Anomalies table: detected anomalies
CREATE TABLE IF NOT EXISTS anomalies (
  id           BIGSERIAL PRIMARY KEY,
  anomaly_id   UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
  type         VARCHAR(30) NOT NULL,
  severity     VARCHAR(10) NOT NULL,
  detected_at  TIMESTAMPTZ NOT NULL,
  resolved_at  TIMESTAMPTZ,
  description  TEXT,
  metadata     JSONB,
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_anomalies_detected ON anomalies (detected_at);
CREATE INDEX idx_anomalies_severity ON anomalies (severity);
CREATE INDEX idx_anomalies_type ON anomalies (type);

-- Transactions table: seeded from ground truth CSV
CREATE TABLE IF NOT EXISTS transactions (
  id             BIGSERIAL PRIMARY KEY,
  order_id       BIGINT,
  invoice_number VARCHAR(30),
  order_date     DATE,
  order_time     TIME,
  customer_number BIGINT,
  customer_name  VARCHAR(100),
  product_name   TEXT,
  brand_name     VARCHAR(100),
  dep_name       VARCHAR(50),
  sub_category   VARCHAR(100),
  salesperson_id INTEGER,
  salesperson_name VARCHAR(100),
  qty            INTEGER,
  gmv            FLOAT,
  nmv            FLOAT,
  total_amount   FLOAT,
  created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_transactions_time ON transactions (order_time);
CREATE INDEX idx_transactions_invoice ON transactions (invoice_number);
CREATE INDEX idx_transactions_date ON transactions (order_date);

-- Insert staff records for reference
CREATE TABLE IF NOT EXISTS staff (
  id               SERIAL PRIMARY KEY,
  salesperson_id   INTEGER NOT NULL UNIQUE,
  employee_code    VARCHAR(20) NOT NULL,
  name             VARCHAR(100) NOT NULL,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO staff (salesperson_id, employee_code, name) VALUES
  (523, 'CL1997', 'Shashikala'),
  (737, 'CL2541', 'Naziya Begum'),
  (971, 'CL2727', 'Zufishan Khazra'),
  (1178, 'CL2063', 'kasthuri v'),
  (1190, 'CL2680', 'Priya v')
ON CONFLICT (salesperson_id) DO NOTHING;
