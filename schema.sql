/*
 Litecord schema file
 */

-- Thank you FrostLuma for giving snowflake_time and time_snowflake
-- convert Discord snowflake to timestamp
CREATE OR REPLACE FUNCTION snowflake_time (snowflake BIGINT)
    RETURNS TIMESTAMP AS $$
BEGIN
    RETURN to_timestamp(((snowflake >> 22) + 1420070400000) / 1000);
END; $$
LANGUAGE PLPGSQL;


-- convert timestamp to Discord snowflake
CREATE OR REPLACE FUNCTION time_snowflake (date TIMESTAMP WITH TIME ZONE)
    RETURNS BIGINT AS $$
BEGIN
    RETURN CAST(EXTRACT(epoch FROM date) * 1000 - 1420070400000 AS BIGINT) << 22;
END; $$
LANGUAGE PLPGSQL;


-- User connection applications
CREATE TABLE IF NOT EXISTS user_conn_apps (
    id serial PRIMARY KEY,
    name text NOT NULL
);

INSERT INTO user_conn_apps (id, name) VALUES (0, 'Twitch');
INSERT INTO user_conn_apps (id, name) VALUES (1, 'Youtube');
INSERT INTO user_conn_apps (id, name) VALUES (2, 'Steam');
INSERT INTO user_conn_apps (id, name) VALUES (3, 'Reddit');
INSERT INTO user_conn_apps (id, name) VALUES (4, 'Facebook');
INSERT INTO user_conn_apps (id, name) VALUES (5, 'Twitter');
INSERT INTO user_conn_apps (id, name) VALUES (6, 'Spotify');
INSERT INTO user_conn_apps (id, name) VALUES (7, 'XBOX');
INSERT INTO user_conn_apps (id, name) VALUES (8, 'Battle.net');
INSERT INTO user_conn_apps (id, name) VALUES (9, 'Skype');
INSERT INTO user_conn_apps (id, name) VALUES (10, 'League of Legends');


CREATE TABLE IF NOT EXISTS files (
    -- snowflake id of the file
    id bigint PRIMARY KEY NOT NULL,

    -- sha512(file)
    hash text NOT NULL,
    mimetype text NOT NULL,

    -- path to the file system
    fspath text NOT NULL
);


CREATE TABLE IF NOT EXISTS users (
    id bigint UNIQUE NOT NULL,
    username varchar(32) NOT NULL,
    discriminator varchar(4) NOT NULL,
    email varchar(255) NOT NULL UNIQUE,

    -- user properties
    bot boolean DEFAULT FALSE,
    mfa_enabled boolean DEFAULT FALSE,
    verified boolean DEFAULT FALSE,
    avatar bigint REFERENCES files (id) DEFAULT NULL,

    -- user badges, discord dev, etc
    flags int DEFAULT 0,

    -- nitro status encoded in here
    premium bool DEFAULT false,

    -- private info
    phone varchar(60) DEFAULT '',
    password_hash text NOT NULL,

    PRIMARY KEY (id, username, discriminator)
);

/*

CREATE TABLE IF NOT EXISTS user_settings (
    id bigint REFERENCES users (id),
    afk_timeout int DEFAULT 300,
    animate_emoji bool DEFAULT true,
    convert_emoticons bool DEFAULT false,
    default_guilds_restricted bool DEFAULT false,
    detect_platform_accounts bool DEFAULT false,

    -- smirk emoji
    developer_mode bool DEFAULT true,

    disable_games_tab bool DEFAULT true,
    enable_tts_command bool DEFAULT false,
    explicit_content_filter int DEFAULT 2,

    friend_source_everyone bool DEFAULT true,
    friend_source_mutuals bool DEFAULT true,
    friend_source_guilds bool DEFAULT true,

    gif_auto_play bool DEFAULT true,
    
    -- TODO: guild_positions
    -- TODO: restricted_guilds

    inline_attachment_media bool DEFAULT true,
    inline_embed_media bool DEFAULT true,
    locale text DEFAULT 'en-US',
    message_display_compact bool DEFAULT false,
    render_embeds bool DEFAULT true,
    render_reactions bool DEFAULT true,
    show_current_game bool DEFAULT true,

    status text DEFAULT 'online' NOT NULL,
    theme text DEFAULT 'dark' NOT NULL,

    timezone_offset int DEFAULT 0,

);

*/

CREATE TABLE IF NOT EXISTS notes (
    user_id bigint REFERENCES users (id),
    target_id bigint REFERENCES users (id),
    note text DEFAULT '',
    PRIMARY KEY (user_id, target_id)
);


CREATE TABLE IF NOT EXISTS connections (
    user_id bigint REFERENCES users (id),
    conn_type bigint REFERENCES user_conn_apps (id),
    name text NOT NULL,
    revoked bool DEFAULT false,
    PRIMARY KEY (user_id, conn_type)
);


CREATE TABLE IF NOT EXISTS channels (
    id bigint PRIMARY KEY,
    channel_type int NOT NULL
);

CREATE TABLE IF NOT EXISTS guilds (
    id bigint PRIMARY KEY NOT NULL,

    name varchar(100) NOT NULL,
    icon text DEFAULT NULL,
    splash text DEFAULT NULL,
    owner_id bigint NOT NULL REFERENCES users (id),

    region text NOT NULL,

    /* default no afk channel 
        afk channel is voice-only.
     */
    afk_channel_id bigint REFERENCES channels (id) DEFAULT NULL,

    /* default 5 minutes */
    afk_timeout int DEFAULT 300,
    
    -- from 0 to 4
    verification_level int DEFAULT 0,

    -- from 0 to 1
    default_message_notifications int DEFAULT 0,

    -- from 0 to 2
    explicit_content_filter int DEFAULT 0,

    -- ????
    mfa_level int DEFAULT 0,

    embed_enabled boolean DEFAULT false,
    embed_channel_id bigint REFERENCES channels (id) DEFAULT NULL,

    widget_enabled boolean DEFAULT false,
    widget_channel_id bigint REFERENCES channels (id) DEFAULT NULL,

    system_channel_id bigint REFERENCES channels (id) DEFAULT NULL
);


CREATE TABLE IF NOT EXISTS guild_channels (
    id bigint REFERENCES channels (id) PRIMARY KEY,
    guild_id bigint REFERENCES guilds (id) ON DELETE CASCADE,

    -- an id to guild_channels
    parent_id bigint DEFAULT NULL,

    name text NOT NULL,
    position int,
    nsfw bool default false
);


CREATE TABLE IF NOT EXISTS guild_text_channels (
    id bigint REFERENCES guild_channels (id) ON DELETE CASCADE,
    topic text DEFAULT '',
    PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS guild_voice_channels (
    id bigint REFERENCES guild_channels (id) ON DELETE CASCADE,

    -- default bitrate for discord is 64kbps
    bitrate int DEFAULT 64,

    -- 0 means infinite
    user_limit int DEFAULT 0,
    PRIMARY KEY (id)
);


CREATE TABLE IF NOT EXISTS dm_channels (
    -- TODO
);


CREATE TABLE IF NOT EXISTS group_dm_channels (
    id bigint REFERENCES channels (id) ON DELETE CASCADE,
    owner_id bigint REFERENCES users (id),
    icon bigint REFERENCES files (id),
    PRIMARY KEY (id)
);


CREATE TABLE IF NOT EXISTS channel_overwrites (
    channel_id bigint REFERENCES channels (id),
    target_id bigint,
    overwrite_type text,
    allow bool default false,
    deny bool default false,
    PRIMARY KEY (channel_id, target_id)
);


CREATE TABLE IF NOT EXISTS guild_features (
    guild_id bigint REFERENCES guilds (id) ON DELETE CASCADE,
    feature text NOT NULL,
    PRIMARY KEY (guild_id, feature)
);


CREATE TABLE IF NOT EXISTS guild_integrations (
    guild_id bigint REFERENCES guilds (id) ON DELETE CASCADE,
    user_id bigint REFERENCES users (id) ON DELETE CASCADE,
    integration bigint REFERENCES user_conn_apps (id),
    PRIMARY KEY (guild_id, user_id)
);


CREATE TABLE IF NOT EXISTS guild_emoji (
    id bigint PRIMARY KEY,
    guild_id bigint REFERENCES guilds (id) ON DELETE CASCADE,
    uploader_id bigint REFERENCES users (id),

    name text NOT NULL,
    image bigint REFERENCES files (id),
    animated bool DEFAULT false,
    managed bool DEFAULT false,
    require_colons bool DEFAULT false
);

/* Someday I might actually write this.
CREATE TABLE IF NOT EXISTS guild_audit_log (
    guild_id bigint REFERENCES guilds (id),

);
*/

CREATE TABLE IF NOT EXISTS invites (
    code text PRIMARY KEY,
    guild_id bigint REFERENCES guilds (id) ON DELETE CASCADE,
    channel_id bigint REFERENCES channels (id) ON DELETE CASCADE,
    inviter bigint REFERENCES users (id),

    created_at timestamp without time zone default now(),
    uses bigint DEFAULT 0,

    -- -1 means infinite here
    max_uses bigint DEFAULT -1,
    max_age bigint DEFAULT -1,

    temporary bool DEFAULT false,
    revoked bool DEFAULT false
);


CREATE TABLE IF NOT EXISTS webhooks (
    id bigint PRIMARY KEY,

    guild_id bigint REFERENCES guilds (id) ON DELETE CASCADE,
    channel_id bigint REFERENCES channels (id) ON DELETE CASCADE,
    creator_id bigint REFERENCES users (id),

    name text NOT NULL,
    avatar text NOT NULL,

    -- Yes, we store the webhook's token
    -- since they aren't users and there's no /api/login for them.
    token text NOT NULL
);




CREATE TABLE IF NOT EXISTS members (
    user_id bigint REFERENCES users (id) ON DELETE CASCADE,
    guild_id bigint REFERENCES guilds (id) ON DELETE CASCADE,
    nickname varchar(100) DEFAULT NULL,
    joined_at timestamp without time zone default now(),
    deafened boolean DEFAULT false,
    muted boolean DEFAULT false,
    PRIMARY KEY (user_id, guild_id)
);


CREATE TABLE IF NOT EXISTS roles (
    id bigint UNIQUE NOT NULL,
    guild_id bigint REFERENCES guilds (id) ON DELETE CASCADE,

    name varchar(100) NOT NULL,
    color int DEFAULT 1,
    hoist bool DEFAULT false,
    position int NOT NULL,
    permissions int NOT NULL,
    managed bool DEFAULT false,
    mentionable bool DEFAULT false,

    PRIMARY KEY (id, guild_id)
);


CREATE TABLE IF NOT EXISTS guild_whitelists (
    emoji_id bigint REFERENCES guild_emoji (id) ON DELETE CASCADE,
    role_id bigint REFERENCES roles (id),
    PRIMARY KEY (emoji_id, role_id)
);

/* Represents a role a member has. */
CREATE TABLE IF NOT EXISTS member_roles (
    user_id bigint REFERENCES users (id) ON DELETE CASCADE,
    guild_id bigint REFERENCES guilds (id) ON DELETE CASCADE,
    role_id bigint REFERENCES roles (id) ON DELETE CASCADE,

    PRIMARY KEY (user_id, guild_id, role_id)
);


CREATE TABLE IF NOT EXISTS bans (
    guild_id bigint REFERENCES guilds (id) ON DELETE CASCADE,

    -- users can be removed but their IDs would still show
    -- on a guild's ban list.
    user_id bigint NOT NULL REFERENCES users (id),

    reason varchar(512) NOT NULL,

    PRIMARY KEY (user_id, guild_id)
);


CREATE TABLE IF NOT EXISTS embeds (
    -- TODO: this table
    id bigint PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS messages (
    id bigint PRIMARY KEY,
    channel_id bigint REFERENCES channels (id),

    -- those are mutually exclusive, only one of them
    -- can NOT be NULL at a time.

    -- if author is NULL -> message from webhook
    -- if webhook is NULL -> message from author
    author_id bigint REFERENCES users (id),
    webhook_id bigint REFERENCES webhooks (id),

    content text,

    created_at timestamp without time zone default now(),
    edited_at timestamp without time zone default NULL,

    tts bool default false,
    mention_everyone bool default false,

    nonce bigint default 0,

    message_type int NOT NULL
);

CREATE TABLE IF NOT EXISTS message_attachments (
    message_id bigint REFERENCES messages (id) UNIQUE,
    attachment bigint REFERENCES files (id),
    PRIMARY KEY (message_id, attachment)
);

CREATE TABLE IF NOT EXISTS message_embeds (
    message_id bigint REFERENCES messages (id) UNIQUE,
    embed_id bigint REFERENCES embeds (id),
    PRIMARY KEY (message_id, embed_id)
);

CREATE TABLE IF NOT EXISTS message_reactions (
    message_id bigint REFERENCES messages (id) UNIQUE,
    user_id bigint REFERENCES users (id),

    -- since it can be a custom emote, or unicode emoji
    emoji_id bigint REFERENCES guild_emoji (id),
    emoji_text text NOT NULL,
    PRIMARY KEY (message_id, user_id)
);

CREATE TABLE IF NOT EXISTS channel_pins (
    channel_id bigint REFERENCES channels (id) UNIQUE,
    message_id bigint REFERENCES messages (id),
    PRIMARY KEY (channel_id, message_id)
);
