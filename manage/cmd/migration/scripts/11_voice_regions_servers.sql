-- voice region data
-- NOTE: do NOT remove any rows. use deprectated=true and
-- DELETE FROM voice_servers instead.
CREATE TABLE IF NOT EXISTS voice_regions (
    -- always lowercase
    id text PRIMARY KEY,

    -- "Russia", "Brazil", "Antartica", etc
    name text NOT NULL,

    -- we don't have the concept of vip guilds yet, but better
    -- future proof.
    vip boolean DEFAULT FALSE,

    deprecated boolean DEFAULT FALSE,

    -- we don't have the concept of custom regions too. we don't have the
    -- concept of official guilds either, but i'm keeping this in
    custom boolean DEFAULT FALSE
);

-- voice server pool. when someone wants to connect to voice, we choose
-- a server that is in the same region the guild is too, and choose the one
-- with the best health value
CREATE TABLE IF NOT EXISTS voice_servers (
    -- hostname is a reachable url, e.g "brazil2.example.com"
    hostname text PRIMARY KEY,
    region_id text REFERENCES voice_regions (id),

    -- health values are more thoroughly defined in the LVSP documentation
    last_health float default 0.5
);


ALTER TABLE guilds DROP COLUMN IF EXISTS region;
ALTER TABLE guilds ADD COLUMN
    region text REFERENCES voice_regions (id);
