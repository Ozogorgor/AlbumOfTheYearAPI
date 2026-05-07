-- Setup mapping table for AOTY Supabase database.
-- Idempotent: safe to re-run. Run in Supabase SQL Editor.

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

-- One-time cleanup: drop the original bogus seed (all three MB IDs returned
-- "Not Found" from MusicBrainz; AOTY slugs for the album entries also pointed
-- at unrelated albums) plus any leftover test mappings from the dev session.
DELETE FROM mb_aoty_mapping WHERE mb_id IN (
    'f21c53c1-31b8-4b97-9a2c-66f70c20f329',  -- bogus Kanye MB ID (real one is 164f0d73-1234-4e2c-8743-d77bf2191051)
    '2ed0a00f-83ef-3544-9315-3d93b96ab66d',  -- bogus Tha Carter V release MB ID
    'b54912aa-1a9f-4310-8c8f-08dbca3c7185',  -- bogus MBDTF release MB ID
    'test-mb-tcv', 'test-dom', 'test-correct-tcv', 'demo-heal'
);

-- Verified seed (MB IDs confirmed against musicbrainz.org/ws/2/, AOTY slugs
-- confirmed by HTTP 200 + canonical title match):
INSERT INTO mb_aoty_mapping (mb_id, type, aoty_slug, name) VALUES
    -- Kanye West (MB lists him as "Ye" since the rename)
    ('164f0d73-1234-4e2c-8743-d77bf2191051', 'artist',
     '183-kanye-west', 'Kanye West'),
    -- My Beautiful Dark Twisted Fantasy (2010 original release-group)
    ('5d6e21e1-deb5-428e-bb42-c2a567f3619b', 'release-group',
     '1998-kanye-west-my-beautiful-dark-twisted-fantasy', 'My Beautiful Dark Twisted Fantasy')
ON CONFLICT (mb_id, type) DO UPDATE SET
    aoty_slug = EXCLUDED.aoty_slug,
    name = EXCLUDED.name;

-- Tha Carter V was in the original seed but the AOTY numeric ID was wrong.
-- Real MB release-group ID: 32ee4338-474b-4d56-bbc8-fdfe5d6dda51
-- AOTY URL not yet confirmed — add via POST /mapping once known, e.g.:
--   curl -X POST -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
--     -d '{"mb_id":"32ee4338-474b-4d56-bbc8-fdfe5d6dda51","type":"release-group",
--          "aoty_slug":"<NUMERIC-ID>-lil-wayne-tha-carter-v","name":"Tha Carter V"}' \
--     https://album-of-the-year-api.vercel.app/mapping

SELECT 'Setup complete' AS status, COUNT(*) AS mapping_count FROM mb_aoty_mapping;
