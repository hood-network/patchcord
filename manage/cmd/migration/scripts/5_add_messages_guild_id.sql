ALTER TABLE messages ADD COLUMN guild_id bigint REFERENCES guilds (id) ON DELETE CASCADE;
