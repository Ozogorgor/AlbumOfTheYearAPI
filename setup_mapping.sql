-- Setup mapping table and initial data for AOTY Supabase database
-- Run this in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS mb_aoty_mapping (
    mb_id TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('artist', 'album', 'release', 'release-group')),
    aoty_slug TEXT NOT NULL,
    name TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (mb_id, type)
);

CREATE INDEX IF NOT EXISTS idx_mb_aoty_mb_id ON mb_aoty_mapping(mb_id);
CREATE INDEX IF NOT EXISTS idx_mb_aoty_type ON mb_aoty_mapping(type);

-- Insert initial mappings
INSERT INTO mb_aoty_mapping (mb_id, type, aoty_slug, name) VALUES
('f21c53c1-31b8-4b97-9a2c-66f70c20f329', 'artist', '183-kanye-west', 'Kanye West'),
('2ed0a00f-83ef-3544-9315-3d93b96ab66d', 'release', '105136-lil-wayne-tha-carter-v', 'Tha Carter V'),
('b54912aa-1a9f-4310-8c8f-08dbca3c7185', 'release', '252305-kanye-west-my-beautiful-dark-twisted-fantasy', 'My Beautiful Dark Twisted Fantasy')
ON CONFLICT (mb_id, type) DO NOTHING;

SELECT 'Setup complete' as status, COUNT(*) as mapping_count FROM mb_aoty_mapping;
