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

-- there was a chain of INSERTs here with hardcoded names and stuff.
-- removed it because we aren't in the best business of hardcoding.

CREATE TABLE IF NOT EXISTS instance_invites (
    code text PRIMARY KEY,

    created_at timestamp without time zone default (now() at time zone 'utc'),

    uses bigint DEFAULT 0,

    -- -1 means infinite uses
    max_uses bigint DEFAULT -1
);




CREATE TABLE IF NOT EXISTS icons (
    -- can be 'user', 'guild', 'emoji'
    scope text NOT NULL,

    -- can be a user snowflake, guild snowflake or
    -- emoji snowflake
    key text,

    -- sha256 of the icon
    hash text UNIQUE,

    -- icon mime
    mime text NOT NULL,
    PRIMARY KEY (scope, key)
);



CREATE TABLE IF NOT EXISTS users (
    id bigint UNIQUE NOT NULL,
    username text NOT NULL,
    discriminator varchar(4) NOT NULL,
    email varchar(255) DEFAULT NULL,

    -- user properties
    bot boolean DEFAULT FALSE,
    mfa_enabled boolean DEFAULT FALSE,
    verified boolean DEFAULT FALSE,
    avatar text REFERENCES icons (hash) DEFAULT NULL,

    -- user badges, discord dev, etc
    flags int DEFAULT 0,

    -- nitro status encoded in here
    premium_since timestamp without time zone default NULL,

    -- private info
    phone varchar(60) DEFAULT '',
    password_hash text NOT NULL,

    -- store the last time the user logged in via the gateway
    last_session timestamp without time zone default (now() at time zone 'utc'),

    PRIMARY KEY (id, username, discriminator)
);


-- main user settings
CREATE TABLE IF NOT EXISTS user_settings (
    id bigint REFERENCES users (id),
    afk_timeout int DEFAULT 300,

    -- connection detection (none by default)
    detect_platform_accounts bool DEFAULT false,

    -- privacy and safety
    -- options like data usage are over
    -- the get_consent function on users blueprint
    default_guilds_restricted bool DEFAULT false,
    explicit_content_filter int DEFAULT 2,
    friend_source jsonb DEFAULT '{"all": true}',

    -- guild positions on the client.
    guild_positions jsonb DEFAULT '[]',

    -- guilds that can't dm you
    restricted_guilds jsonb DEFAULT '[]',

    render_reactions bool DEFAULT true,

    -- show the current palying game
    -- as an activity
    show_current_game bool DEFAULT true,

    -- text and images

    -- show MEDIA embeds for urls
    inline_embed_media bool DEFAULT true,

    -- show thumbnails for attachments
    inline_attachment_media bool DEFAULT true,

    -- autoplay gifs on the client
    gif_auto_play bool DEFAULT true,

    -- render OpenGraph embeds for urls posted in chat
    render_embeds bool DEFAULT true,

    -- play animated emojis
    animate_emoji bool DEFAULT true,

    -- convert :-) to the smile emoji and others
    convert_emoticons bool DEFAULT false,

    -- enable /tts
    enable_tts_command bool DEFAULT false,

    -- appearance
    message_display_compact bool DEFAULT false,

    -- for now we store status but don't
    -- actively use it, since the official client
    -- sends its own presence on IDENTIFY
    status text DEFAULT 'online' NOT NULL,
    theme text DEFAULT 'dark' NOT NULL,
    developer_mode bool DEFAULT true,
    disable_games_tab bool DEFAULT true,
    locale text DEFAULT 'en-US',

    -- set by the client
    -- the server uses this to make emails
    -- about "look at what youve missed"
    timezone_offset int DEFAULT 0
);


-- main user billing tables
CREATE TABLE IF NOT EXISTS user_payment_sources (
    id bigint PRIMARY KEY,
    user_id bigint REFERENCES users (id) NOT NULL,

    -- type=1: credit card fields
    -- type=2: paypal fields
    source_type int,

    -- idk lol
    invalid bool DEFAULT false,
    default_ bool DEFAULT false,

    -- credit card info (type 1 only)
    expires_month int DEFAULT 12,
    expires_year int DEFAULT 3000,
    brand text,
    cc_full text NOT NULL,

    -- paypal info (type 2 only)
    paypal_email text DEFAULT 'a@a.com',

    -- applies to both
    billing_address jsonb DEFAULT '{}'
);

-- actual subscription statuses
CREATE TABLE IF NOT EXISTS user_subscriptions (
    id bigint PRIMARY KEY,
    source_id bigint REFERENCES user_payment_sources (id) NOT NULL,
    user_id bigint REFERENCES users (id) NOT NULL,

    -- s_type = 1: purchase
    -- s_type = 2: upgrade
    s_type int DEFAULT 1,

    -- gateway = 1: stripe
    -- gateway = 2: braintree
    payment_gateway int DEFAULT 0,

    -- "premium_<month|year>_tier_<int>"
    payment_gateway_plan_id text,

    -- status = 1: active
    -- status = 3: cancelled
    status int DEFAULT 1,

    canceled_at timestamp without time zone default NULL,

    -- set by us
    period_start timestamp without time zone default (now() at time zone 'utc'),
    period_end timestamp without time zone default NULL
);

-- payment logs
CREATE TABLE IF NOT EXISTS user_payments (
    id bigint PRIMARY KEY,

    -- NOTE: has ON DELETE SET NULL (migration 4)
    source_id bigint REFERENCES user_payment_sources (id),

    -- NOTE: has ON DELETE SET NULL (migration 4)
    subscription_id bigint REFERENCES user_subscriptions (id),

    -- NOTE: has ON DELETE SET NULL (migration 4)
    user_id bigint REFERENCES users (id),

    currency text DEFAULT 'usd',

    -- status = 1: success
    -- status = 2: failed
    status int DEFAULT 1,

    -- 499 = 4 dollars 99 cents
    amount bigint,

    tax int DEFAULT 0,
    tax_inclusive BOOL default true,

    description text,

    amount_refunded int DEFAULT 0
);


-- main user relationships
CREATE TABLE IF NOT EXISTS relationships (
    -- the id of who made the relationship
    user_id bigint REFERENCES users (id),

    -- the id of the peer who got a friendship
    -- request or a block.
    peer_id bigint REFERENCES users (id),

    rel_type SMALLINT,

    PRIMARY KEY (user_id, peer_id)
);


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

CREATE TABLE IF NOT EXISTS user_read_state (
    user_id bigint REFERENCES users (id),

    -- NOTE: has ON DELETE CASCADE (migration 4)
    channel_id bigint REFERENCES channels (id),

    -- we don't really need to link
    -- this column to the messages table
    last_message_id bigint,

    -- counts are always positive
    mention_count bigint CHECK (mention_count > -1),

    PRIMARY KEY (user_id, channel_id)
);


-- voice region data
-- NOTE: do NOT remove any rows. use deprectated=true and
-- DELETE FROM voice_servers instead.
CREATE TABLE IF NOT EXISTS voice_regions (
    -- always lowercase
    id text PRIMARY KEY,

    -- "Russia", "Brazil", "Antartica", etc
    name text NOT NULL,

    -- we don't have the concept of vip guilds yet, but better
    -- future proof.
    vip boolean DEFAULT FALSE,

    deprecated boolean DEFAULT FALSE,

    -- we don't have the concept of custom regions too. we don't have the
    -- concept of official guilds either, but i'm keeping this in
    custom boolean DEFAULT FALSE
);

-- voice server pool. when someone wants to connect to voice, we choose
-- a server that is in the same region the guild is too, and choose the one
-- with the best health value
CREATE TABLE IF NOT EXISTS voice_servers (
    -- hostname is a reachable url, e.g "brazil2.example.com"
    hostname text PRIMARY KEY,

    -- NOTE: has ON DELETE CASCADE (migration 4)
    region_id text REFERENCES voice_regions (id),

    -- health values are more thoroughly defined in the LVSP documentation
    last_health float default 0.5
);

CREATE TABLE IF NOT EXISTS guilds (
    id bigint PRIMARY KEY NOT NULL,

    name text NOT NULL,
    icon text DEFAULT NULL,
    splash text DEFAULT NULL,
    owner_id bigint NOT NULL REFERENCES users (id),

    region text REFERENCES voice_regions (id),

    features text[],

    -- default no afk channel 
    -- afk channel is voice-only.
    afk_channel_id bigint REFERENCES channels (id) DEFAULT NULL,

    -- default 5 minutes
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

    system_channel_id bigint REFERENCES channels (id) DEFAULT NULL,

    -- only for guilds with certain features
    description text DEFAULT NULL,
    banner text DEFAULT NULL
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
    rate_limit_per_user bigint DEFAULT 0,
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


CREATE TABLE IF NOT EXISTS guild_settings (
    -- NOTE: migration 13 fixes table constraints to point to
    -- members instead of users this prevents descynrhonization
    -- on a member leave/kick/ban
    user_id bigint REFERENCES users (id) ON DELETE CASCADE,
    guild_id bigint REFERENCES guilds (id) ON DELETE CASCADE,

    suppress_everyone bool DEFAULT false,
    muted bool DEFAULT false,
    message_notifications int DEFAULT 0,
    mobile_push bool DEFAULT true,

    PRIMARY KEY (user_id, guild_id)
);


CREATE TABLE IF NOT EXISTS guild_settings_channel_overrides (
    user_id bigint REFERENCES users (id) ON DELETE CASCADE,
    guild_id bigint REFERENCES guilds (id) ON DELETE CASCADE,
    channel_id bigint REFERENCES channels (id) ON DELETE CASCADE,

    muted bool DEFAULT false,
    message_notifications int DEFAULT 0,

    PRIMARY KEY (user_id, guild_id, channel_id)
);

CREATE TABLE IF NOT EXISTS dm_channels (
    id bigint REFERENCES channels (id) ON DELETE CASCADE UNIQUE,

    party1_id bigint REFERENCES users (id) ON DELETE CASCADE,
    party2_id bigint REFERENCES users (id) ON DELETE CASCADE,

    PRIMARY KEY (id, party1_id, party2_id)
);


CREATE TABLE IF NOT EXISTS dm_channel_state (
    user_id bigint REFERENCES users (id) ON DELETE CASCADE,
    dm_id bigint REFERENCES dm_channels (id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, dm_id)
);


CREATE TABLE IF NOT EXISTS group_dm_channels (
    id bigint REFERENCES channels (id) ON DELETE CASCADE,
    owner_id bigint REFERENCES users (id),
    name text,
    icon text REFERENCES icons (hash) DEFAULT NULL,
    PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS group_dm_members (
    id bigint REFERENCES group_dm_channels (id) ON DELETE CASCADE,
    member_id bigint REFERENCES users (id),
    PRIMARY KEY (id, member_id)
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
    image text REFERENCES icons (hash),
    animated bool DEFAULT false,
    managed bool DEFAULT false,
    require_colons bool DEFAULT true
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

    created_at timestamp without time zone default (now() at time zone 'utc'),
    uses bigint DEFAULT 0,

    -- -1 means infinite here
    max_uses bigint DEFAULT -1,
    max_age bigint DEFAULT -1,

    temporary bool DEFAULT false,
    revoked bool DEFAULT false
);

-- vanity url table, the mapping is 1-1 for guilds and vanity urls
CREATE TABLE IF NOT EXISTS vanity_invites (
    -- NOTE: has ON DELETE CASCADE (migration 4)
    guild_id bigint REFERENCES guilds (id) PRIMARY KEY,
    code text REFERENCES invites (code) ON DELETE CASCADE
);


CREATE TABLE IF NOT EXISTS webhooks (
    id bigint PRIMARY KEY,

    guild_id bigint REFERENCES guilds (id) ON DELETE CASCADE,
    channel_id bigint REFERENCES channels (id) ON DELETE CASCADE,
    creator_id bigint REFERENCES users (id),

    name text NOT NULL,
    avatar text DEFAULT NULL,

    -- Yes, we store the webhook's token
    -- since they aren't users and there's no /api/login for them.
    token text NOT NULL
);


CREATE TABLE IF NOT EXISTS members (
    user_id bigint REFERENCES users (id) ON DELETE CASCADE,
    guild_id bigint REFERENCES guilds (id) ON DELETE CASCADE,
    nickname text DEFAULT NULL,
    joined_at timestamp without time zone default (now() at time zone 'utc'),
    deafened boolean DEFAULT false,
    muted boolean DEFAULT false,
    PRIMARY KEY (user_id, guild_id)
);


CREATE TABLE IF NOT EXISTS roles (
    id bigint UNIQUE NOT NULL,
    guild_id bigint REFERENCES guilds (id) ON DELETE CASCADE,

    name text NOT NULL,
    color int DEFAULT 0,
    hoist bool DEFAULT false,
    position int NOT NULL,
    permissions int NOT NULL,
    managed bool DEFAULT false,
    mentionable bool DEFAULT false,

    PRIMARY KEY (id, guild_id)
);


CREATE TABLE IF NOT EXISTS channel_overwrites (
    channel_id bigint REFERENCES channels (id) ON DELETE CASCADE,

    -- target_type = 0 -> use target_user
    -- target_type = 1 -> use target_role
    -- discord already has overwrite.type = 'role' | 'member'
    -- so this allows us to be more compliant with the API
    target_type integer default null,

    -- keeping both columns separated and as foreign keys
    -- instead of a single "target_id bigint" column
    -- makes us able to remove the channel overwrites of
    -- a role when its deleted (same for users, etc).
    target_role bigint REFERENCES roles (id) ON DELETE CASCADE,
    -- NOTE: migration 13 fixes table constraints to point to
    -- members instead of users this prevents descynrhonization
    -- on a member leave/kick/ban
    target_user bigint REFERENCES users (id) ON DELETE CASCADE,

    -- since those are permission bit sets
    -- they're bigints (64bits), discord,
    -- for now, only needs 53.
    allow bigint DEFAULT 0,
    deny bigint DEFAULT 0
);

-- columns in private keys can't have NULL values,
-- so instead we use a custom constraint with UNIQUE

ALTER TABLE channel_overwrites
    DROP CONSTRAINT IF EXISTS channel_overwrites_uniq;
ALTER TABLE channel_overwrites
    ADD CONSTRAINT channel_overwrites_uniq
    UNIQUE (channel_id, target_role, target_user);


CREATE TABLE IF NOT EXISTS guild_whitelists (
    emoji_id bigint REFERENCES guild_emoji (id) ON DELETE CASCADE,
    role_id bigint REFERENCES roles (id),
    PRIMARY KEY (emoji_id, role_id)
);

/* Represents a role a member has. */
CREATE TABLE IF NOT EXISTS member_roles (
    -- NOTE: migration 13 fixes table constraints to point to
    -- members instead of users this prevents descynrhonization
    -- on a member leave/kick/ban
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

    reason text NOT NULL,

    PRIMARY KEY (user_id, guild_id)
);


CREATE TABLE IF NOT EXISTS messages (
    id bigint PRIMARY KEY,
    channel_id bigint REFERENCES channels (id) ON DELETE CASCADE,

    -- this is good for search.
    guild_id bigint REFERENCES guilds (id) ON DELETE CASCADE,

    -- if author is NULL -> message from webhook ->
    -- fetch from message_webhook_info
    author_id bigint REFERENCES users (id),

    content text,

    created_at timestamp without time zone default (now() at time zone 'utc'),
    edited_at timestamp without time zone default NULL,

    tts bool default false,
    mention_everyone bool default false,

    embeds jsonb DEFAULT '[]',

    nonce bigint default 0,

    message_type int NOT NULL
);


CREATE TABLE IF NOT EXISTS message_webhook_info (
    message_id bigint REFERENCES messages (id) PRIMARY KEY,

    webhook_id bigint,
    name text DEFAULT '<invalid>',
    avatar text DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS message_reactions (
    message_id bigint REFERENCES messages (id),
    user_id bigint REFERENCES users (id),

    react_ts timestamp without time zone default (now() at time zone 'utc'),

    -- emoji_type = 0 -> custom emoji
    -- emoji_type = 1 -> unicode emoji
    emoji_type int DEFAULT 0,
    emoji_id bigint REFERENCES guild_emoji (id),
    emoji_text text
);

-- unique constraint over multiple columns instead of a primary key
ALTER TABLE message_reactions
    DROP CONSTRAINT IF EXISTS message_reactions_main_uniq;
ALTER TABLE message_reactions
    ADD CONSTRAINT message_reactions_main_uniq
    UNIQUE (message_id, user_id, emoji_id, emoji_text);

CREATE TABLE IF NOT EXISTS channel_pins (
    channel_id bigint REFERENCES channels (id) ON DELETE CASCADE,
    message_id bigint REFERENCES messages (id) ON DELETE CASCADE,
    PRIMARY KEY (channel_id, message_id)
);


-- main attachments table
CREATE TABLE IF NOT EXISTS attachments (
    id bigint PRIMARY KEY,

    -- keeping channel_id and message_id
    -- make a way "better" attachment url.

    -- NOTE: has ON DELETE CASCADE (migration 4)
    channel_id bigint REFERENCES channels (id),
    message_id bigint REFERENCES messages (id),

    filename text NOT NULL,
    filesize integer,

    image boolean DEFAULT FALSE,

    -- only not null if image=true
    height integer DEFAULT NULL,
    width integer DEFAULT NULL
);
