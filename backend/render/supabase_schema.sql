-- supabase_schema.sql
-- Run this in your Supabase project's SQL Editor to set up the required tables.

-- Stores the current Upstox access token (updated daily via POST /set-token)
CREATE TABLE IF NOT EXISTS tokens (
    id         int  PRIMARY KEY DEFAULT 1,  -- single-row table
    token      text NOT NULL,
    updated_at timestamptz DEFAULT now()
);

-- Stores each option chain snapshot collected by the Render service
CREATE TABLE IF NOT EXISTS option_snapshots (
    id          bigserial    PRIMARY KEY,
    index_name  text         NOT NULL,        -- "Nifty" | "BankNifty" | "Sensex"
    expiry_date text         NOT NULL,        -- "YYYY-MM-DD"
    captured_at timestamptz  DEFAULT now(),
    data        jsonb        NOT NULL,        -- array of row objects (±20 strikes)
    synced      boolean      DEFAULT false    -- true after local app downloads it
);

-- Index for fast unsynced queries
CREATE INDEX IF NOT EXISTS idx_snapshots_synced
    ON option_snapshots (synced, captured_at);
