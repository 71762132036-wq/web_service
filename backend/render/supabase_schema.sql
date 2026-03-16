-- supabase_schema.sql
-- Run this in your Supabase project's SQL Editor to set up the required tables.

-- Stores the current Upstox access token (updated daily via POST /set-token)
CREATE TABLE IF NOT EXISTS tokens (
    id         int  PRIMARY KEY DEFAULT 1,  -- single-row table
    token      text NOT NULL,
    updated_at timestamptz DEFAULT now()
);

-- Stores each option chain snapshot collected by the Render service.
-- captured_at is stored in IST (Asia/Kolkata) so that filenames on the
-- local machine match the clock directly without UTC→IST conversion.
-- Rows are hard-deleted by the local sync router after successful download.
CREATE TABLE IF NOT EXISTS option_snapshots (
    id          bigserial    PRIMARY KEY,
    index_name  text         NOT NULL,        -- "Nifty" | "BankNifty" | "Sensex"
    expiry_date text         NOT NULL,        -- "YYYY-MM-DD"
    captured_at timestamptz  DEFAULT now(),   -- stored in IST
    data        jsonb        NOT NULL,        -- array of row objects (±20 strikes)
    synced      boolean      DEFAULT false    -- deprecated; rows are deleted after sync
);

-- Index for fast time-ordered queries
CREATE INDEX IF NOT EXISTS idx_snapshots_captured_at
    ON option_snapshots (captured_at);

