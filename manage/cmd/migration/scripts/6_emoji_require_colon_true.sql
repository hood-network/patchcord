-- require_colons seems to be true for all custom emoji.
ALTER TABLE guild_emoji ALTER COLUMN require_colons SET DEFAULT true;

-- retroactively update all other emojis
UPDATE guild_emoji SET require_colons=true;
