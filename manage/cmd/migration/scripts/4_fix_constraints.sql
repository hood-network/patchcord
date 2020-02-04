ALTER TABLE attachments
    DROP CONSTRAINT IF EXISTS attachments_channel_id_fkey,
    DROP CONSTRAINT IF EXISTS attachments_message_id_fkey,
    ADD CONSTRAINT attachments_channel_id_fkey
        FOREIGN KEY (channel_id)
        REFERENCES channels (id)
        ON DELETE CASCADE,
    ADD CONSTRAINT attachments_message_id_fkey
        FOREIGN KEY (message_id)
        REFERENCES messages (id)
        ON DELETE CASCADE;

ALTER TABLE user_payments
    DROP CONSTRAINT IF EXISTS user_payments_source_id_fkey,
    DROP CONSTRAINT IF EXISTS user_payments_subscription_id_fkey,
    DROP CONSTRAINT IF EXISTS user_payments_user_id_fkey,
    ADD CONSTRAINT user_payments_source_id_fkey
        FOREIGN KEY (source_id)
        REFERENCES user_payment_sources (id)
        ON DELETE SET NULL,
    ADD CONSTRAINT user_payments_subscription_id_fkey
        FOREIGN KEY (subscription_id)
        REFERENCES user_subscriptions (id)
        ON DELETE SET NULL,
    ADD CONSTRAINT user_payments_user_id_fkey
        FOREIGN KEY (user_id)
        REFERENCES users (id)
        ON DELETE SET NULL;

ALTER TABLE user_read_state
    DROP CONSTRAINT IF EXISTS user_read_state_channel_id_fkey,
    ADD CONSTRAINT user_read_state_channel_id_fkey
        FOREIGN KEY (channel_id)
        REFERENCES channels (id)
        ON DELETE CASCADE;

ALTER TABLE voice_servers
    DROP CONSTRAINT IF EXISTS voice_servers_region_id_fkey,
    ADD CONSTRAINT voice_servers_region_id_fkey
        FOREIGN KEY (region_id)
        REFERENCES voice_regions (id)
        ON DELETE CASCADE;

ALTER TABLE guilds
    DROP CONSTRAINT IF EXISTS guilds_region_fkey,
    DROP CONSTRAINT IF EXISTS guilds_afk_channel_id_fkey,
    DROP CONSTRAINT IF EXISTS guilds_embed_channel_id_fkey,
    DROP CONSTRAINT IF EXISTS guilds_widget_channel_id_fkey,
    DROP CONSTRAINT IF EXISTS guilds_system_channel_id_fkey,
    ADD CONSTRAINT guilds_region_fkey
        FOREIGN KEY (region)
        REFERENCES voice_regions (id)
        ON DELETE SET NULL,
    ADD CONSTRAINT guilds_afk_channel_id_fkey
        FOREIGN KEY (afk_channel_id)
        REFERENCES channels (id)
        ON DELETE SET DEFAULT,
    ADD CONSTRAINT guilds_embed_channel_id_fkey
        FOREIGN KEY (embed_channel_id)
        REFERENCES channels (id)
        ON DELETE SET DEFAULT,
    ADD CONSTRAINT guilds_widget_channel_id_fkey
        FOREIGN KEY (widget_channel_id)
        REFERENCES channels (id)
        ON DELETE SET DEFAULT,
    ADD CONSTRAINT guilds_system_channel_id_fkey
        FOREIGN KEY (system_channel_id)
        REFERENCES channels (id)
        ON DELETE SET DEFAULT;

ALTER TABLE guild_channels
    DROP CONSTRAINT IF EXISTS guild_channels_id_fkey,
    ADD CONSTRAINT guild_channels_id_fkey 
        FOREIGN KEY (id)
        REFERENCES channels (id)
        ON DELETE CASCADE;

ALTER TABLE group_dm_channels
    DROP CONSTRAINT IF EXISTS group_dm_channels_icon_fkey,
    ADD CONSTRAINT group_dm_channels_icon_fkey
        FOREIGN KEY (icon)
        REFERENCES icons (hash)
        ON DELETE SET DEFAULT;

ALTER TABLE guild_emoji
    DROP CONSTRAINT IF EXISTS guild_emoji_image_fkey,
    ADD CONSTRAINT guild_emoji_image_fkey
        FOREIGN KEY (image)
        REFERENCES icons (hash)
        ON DELETE CASCADE;

ALTER TABLE vanity_invites
    DROP CONSTRAINT IF EXISTS vanity_invites_guild_id_fkey,
    ADD CONSTRAINT vanity_invites_guild_id_fkey
        FOREIGN KEY (guild_id)
        REFERENCES guilds (id)
        ON DELETE CASCADE;

ALTER TABLE guild_whitelists
    DROP CONSTRAINT IF EXISTS guild_whitelists_role_id_fkey,
    ADD CONSTRAINT guild_whitelists_role_id_fkey
        FOREIGN KEY (role_id)
        REFERENCES roles (id)
        ON DELETE CASCADE;

ALTER TABLE message_webhook_info
    DROP CONSTRAINT IF EXISTS message_webhook_info_message_id_fkey,
    ADD CONSTRAINT message_webhook_info_message_id_fkey
        FOREIGN KEY (message_id)
        REFERENCES messages (id)
        ON DELETE CASCADE;

ALTER TABLE message_reactions
    DROP CONSTRAINT IF EXISTS message_reactions_message_id_fkey,
    DROP CONSTRAINT IF EXISTS message_reactions_emoji_id_fkey,
    ADD CONSTRAINT message_reactions_message_id_fkey
        FOREIGN KEY (message_id)
        REFERENCES messages (id)
        ON DELETE CASCADE,
    ADD CONSTRAINT message_reactions_emoji_id_fkey
        FOREIGN KEY (emoji_id)
        REFERENCES guild_emoji (id)
        ON DELETE CASCADE;

ALTER TABLE attachments
    DROP CONSTRAINT IF EXISTS attachments_message_id_fkey,
    DROP CONSTRAINT IF EXISTS attachments_channel_id_fkey,
    ADD CONSTRAINT attachments_message_id_fkey
        FOREIGN KEY (message_id)
        REFERENCES messages (id)
        ON DELETE CASCADE,
    ADD CONSTRAINT attachments_channel_id_fkey
        FOREIGN KEY (channel_id)
        REFERENCES channels (id)
        ON DELETE CASCADE;

