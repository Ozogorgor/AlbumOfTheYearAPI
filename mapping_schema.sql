-- Add mapping table for MusicBrainz ID → AOTY slug
CREATE TABLE IF NOT EXISTS mb_aoty_mapping (
    mb_artist_id TEXT PRIMARY KEY,
    aoty_slug TEXT NOT NULL,
    artist_name TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Cache table (already in cache_schema.sql)
CREATE TABLE IF NOT EXISTS cache (
    id_key TEXT PRIMARY KEY,
    data JSONB NOT NULL,
    cached_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Optional: Add index for faster lookups
CREATE INDEX IF NOT EXISTS idx_cache_key ON cache(id_key);
CREATE INDEX IF NOT EXISTS idx_mb_aoty_mb_id ON mb_aoty_mapping(mb_artist_id);
