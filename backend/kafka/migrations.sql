-- ─────────────────────────────────────────────────────────────────────────────
-- Kafka-related schema additions for Flowdesk CRM
-- Run once: psql $DATABASE_URL -f kafka/migrations.sql
-- ─────────────────────────────────────────────────────────────────────────────

-- Persisted leads (replaces the in-memory _LEADS list)
CREATE TABLE IF NOT EXISTS leads (
    id         SERIAL PRIMARY KEY,
    name       VARCHAR(255) NOT NULL,
    phone      VARCHAR(50)  NOT NULL,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Dead-letter store: Kafka messages that could not be published/processed
CREATE TABLE IF NOT EXISTS kafka_errors (
    id            SERIAL PRIMARY KEY,
    topic         VARCHAR(255) NOT NULL,
    payload       JSONB        NOT NULL,
    error_message TEXT,
    retry_count   INTEGER      NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Audit log: one row per lead event processed by the consumer
CREATE TABLE IF NOT EXISTS lead_events (
    id            SERIAL PRIMARY KEY,
    lead_id       INTEGER      NOT NULL,
    name          VARCHAR(255),
    phone         VARCHAR(50),
    event_type    VARCHAR(50)  NOT NULL DEFAULT 'created',
    whatsapp_sid  VARCHAR(255),
    email_sent    BOOLEAN      NOT NULL DEFAULT FALSE,
    error         TEXT,
    processed_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kafka_errors_topic      ON kafka_errors (topic, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_lead_events_lead_id     ON lead_events  (lead_id);
