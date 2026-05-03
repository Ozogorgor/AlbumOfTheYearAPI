-- Update mapping table to support both artist + album lookups
CREATE TABLE IF NOT EXISTS mb_aoty_mapping (
    mb_id TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('artist', 'album', 'release', 'release-group')),
    aoty_slug TEXT NOT NULL,
    name TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (mb_id, type)
);

-- Cache table (already exists)
CREATE TABLE IF NOT EXISTS cache (
    id_key TEXT PRIMARY KEY,
    data JSONB NOT NULL,
    cached_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes for faster lookups
CREATE INDEX IF NOT EXISTS idx_mb_aoty_mb_id ON mb_aoty_mapping(mb_id);
CREATE INDEX IF NOT EXISTS idx_mb_aoty_type ON mb_aoty_mapping(type);
CREATE INDEX IF NOT EXISTS idx_cache_key ON cache(id_key);
