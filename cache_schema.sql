-- Cache table for AlbumOfTheYearAPI
-- Run this in your PostgreSQL database (Supabase SQL Editor)

CREATE TABLE IF NOT EXISTS cache (
    id_key TEXT PRIMARY KEY,
    data JSONB NOT NULL,
    cached_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Optional: auto-cleanup old entries
-- DELETE FROM cache WHERE cached_at < NOW() - INTERVAL '30 days';
