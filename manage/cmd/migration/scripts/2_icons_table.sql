
-- new icons table
CREATE TABLE IF NOT EXISTS icons (
    scope text NOT NULL,
    key text,
    hash text UNIQUE NOT NULL,
    mime text NOT NULL,
    PRIMARY KEY (scope, hash, mime)
);

-- dummy attachments table for now.
CREATE TABLE IF NOT EXISTS attachments (
    id bigint NOT NULL,
    PRIMARY KEY (id)
);

-- remove the old columns referencing the files table
ALTER TABLE users DROP COLUMN avatar;
ALTER TABLE users ADD COLUMN avatar text REFERENCES icons (hash) DEFAULT NULL;

ALTER TABLE group_dm_channels DROP COLUMN icon;
ALTER TABLE group_dm_channels ADD COLUMN icon text REFERENCES icons (hash);

ALTER TABLE guild_emoji DROP COLUMN image;
ALTER TABLE guild_emoji ADD COLUMN image text REFERENCES icons (hash);

ALTER TABLE guilds DROP COLUMN icon;
ALTER TABLE guilds ADD COLUMN icon text REFERENCES icons (hash) DEFAULT NULL;

-- this one is a change from files to the attachments table
ALTER TABLE message_attachments DROP COLUMN attachment;
ALTER TABLE guild_emoji ADD COLUMN attachment bigint REFERENCES attachments (id);

-- remove files table
DROP TABLE files;
