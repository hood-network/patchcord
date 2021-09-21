BEGIN TRANSACTION;

DELETE
FROM guild_settings
WHERE NOT EXISTS(
    SELECT members.user_id
    FROM members
    WHERE members.user_id = guild_settings.user_id
        AND members.guild_id = guild_settings.guild_id
);

ALTER TABLE guild_settings
    DROP CONSTRAINT IF EXISTS guild_settings_user_id_fkey,
    DROP CONSTRAINT IF EXISTS guild_settings_guild_id_fkey,
    ADD CONSTRAINT guild_settings_user_id_guild_id_fkey
        FOREIGN KEY (user_id, guild_id)
        REFERENCES members (user_id, guild_id)
        ON DELETE CASCADE;

DELETE
FROM member_roles
WHERE NOT EXISTS(
    SELECT members.user_id
    FROM members
    WHERE members.user_id = member_roles.user_id
        AND members.guild_id = member_roles.guild_id
);

ALTER TABLE member_roles
    DROP CONSTRAINT IF EXISTS member_roles_user_id_fkey,
    DROP CONSTRAINT IF EXISTS member_roles_guild_id_fkey,
    ADD CONSTRAINT member_roles_user_id_guild_id_fkey
        FOREIGN KEY (user_id, guild_id)
        REFERENCES members (user_id, guild_id)
        ON DELETE CASCADE;

-- To make channel_overwrites aware of guilds, we need to backfill the column
-- with data from the guild_channels table. after that, we can make a proper
-- foreign key to the members table!

ALTER TABLE channel_overwrites
    ADD COLUMN guild_id bigint DEFAULT NULL;

UPDATE channel_overwrites 
    SET guild_id = guild_channels.guild_id 
    FROM guild_channels
    WHERE guild_channels.id = channel_overwrites.channel_id;

ALTER TABLE channel_overwrites
    ALTER COLUMN guild_id DROP DEFAULT,
    ALTER COLUMN guild_id SET NOT NULL;

ALTER TABLE channel_overwrites
    DROP CONSTRAINT IF EXISTS channel_overwrites_target_user_fkey,
    ADD CONSTRAINT channel_overwrites_target_user_guild_id_fkey
        FOREIGN KEY (target_user, guild_id)
        REFERENCES members (user_id, guild_id)
        ON DELETE CASCADE;

COMMIT;
