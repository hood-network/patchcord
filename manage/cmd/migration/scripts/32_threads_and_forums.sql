ALTER TABLE channels
    ADD COLUMN flags int NOT NULL DEFAULT 0;

ALTER TABLE guild_channels
    ADD COLUMN default_auto_archive_duration int default 1440;

CREATE TABLE IF NOT EXISTS guild_threads (
    id bigint REFERENCES channels (id) PRIMARY KEY,
    guild_id bigint REFERENCES guilds (id) ON DELETE CASCADE,

    parent_id bigint REFERENCES guild_text_channels (id) DEFAULT NULL ON DELETE CASCADE,
    owner_id bigint REFERENCES users (id) NOT NULL,

    name text NOT NULL,
    archived bool DEFAULT false,
    locked bool DEFAULT false,
    create_timestamp timestamp without time zone default (now() at time zone 'utc'),
    archive_timestamp timestamp without time zone default NULL,
    active_timestamp timestamp without time zone default (now() at time zone 'utc'),
    rate_limit_per_user bigint DEFAULT 0,
    auto_archive_duration int DEFAULT 1440,
    total_message_sent bigint DEFAULT 0,
);

CREATE TABLE IF NOT EXISTS thread_members (
    id bigint REFERENCES guild_threads (id) ON DELETE CASCADE,
    user_id bigint NOT NULL
    flags int NOT NULL DEFAULT 0,
    muted bool DEFAULT false,
    mute_config jsonb DEFAULT '{}',
    join_timestamp timestamp without time zone default (now() at time zone 'utc'),
);
