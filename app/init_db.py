"""
Initialize database tables for AOTY API
Run this once to set up the mapping table
"""
import os
import psycopg2

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("DATABASE_URL not set")
    exit(1)

try:
    conn = psycopg2.connect(DATABASE_URL, connect_timeout=5)
    cur = conn.cursor()

    # Create mapping table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mb_aoty_mapping (
            mb_id TEXT NOT NULL,
            type TEXT NOT NULL,
            aoty_slug TEXT NOT NULL,
            name TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            PRIMARY KEY (mb_id, type)
        )
    """)

    # Create indexes
    cur.execute("CREATE INDEX IF NOT EXISTS idx_mb_aoty_mb_id ON mb_aoty_mapping(mb_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_mb_aoty_type ON mb_aoty_mapping(type)")

    # Insert initial mappings
    cur.execute("""
        INSERT INTO mb_aoty_mapping (mb_id, type, aoty_slug, name) VALUES
        ('f21c53c1-31b8-4b97-9a2c-66f70c20f329', 'artist', '183-kanye-west', 'Kanye West'),
        ('2ed0a00f-83ef-3544-9315-3d93b96ab66d', 'release', '105136-lil-wayne-tha-carter-v', 'Tha Carter V')
        ON CONFLICT (mb_id, type) DO NOTHING
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("Database initialized successfully")
except Exception as e:
    print(f"Error: {e}")
