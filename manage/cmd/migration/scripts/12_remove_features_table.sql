DROP TABLE guild_features;
DROP TABLE features;

-- this should do the trick
ALTER TABLE guilds ADD COLUMN features text[] NOT NULL DEFAULT '{}';
