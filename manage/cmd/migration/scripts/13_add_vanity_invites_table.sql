-- vanity url table, the mapping is 1-1 for guilds and vanity urls
CREATE TABLE IF NOT EXISTS vanity_invites (
    guild_id bigint REFERENCES guilds (id) PRIMARY KEY,
    code text REFERENCES invites (code) ON DELETE CASCADE
);
