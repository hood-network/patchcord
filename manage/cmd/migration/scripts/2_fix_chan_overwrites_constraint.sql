ALTER TABLE channel_overwrites
    DROP CONSTRAINT IF EXISTS channel_overwrites_uniq;

ALTER TABLE channel_overwrites
    ADD CONSTRAINT channel_overwrites_target_role_uniq
    UNIQUE (channel_id, target_role);

ALTER TABLE channel_overwrites
    ADD CONSTRAINT channel_overwrites_target_user_uniq
    UNIQUE (channel_id, target_user);
