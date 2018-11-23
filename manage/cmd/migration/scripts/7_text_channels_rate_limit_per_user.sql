ALTER TABLE guild_text_channels
ADD COLUMN rate_limit_per_user bigint DEFAULT 0;
