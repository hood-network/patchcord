DROP TABLE guild_features;
DROP TABLE features;

ALTER TABLE guilds ADD COLUMN features text[];
