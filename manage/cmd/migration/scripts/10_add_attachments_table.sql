CREATE TABLE IF NOT EXISTS attachments (
    id bigint PRIMARY KEY,

    channel_id bigint REFERENCES channels (id),
    message_id bigint REFERENCES messages (id),

    filename text NOT NULL,
    filesize integer,

    image boolean DEFAULT FALSE,

    -- only not null if image=true
    height integer DEFAULT NULL,
    width integer DEFAULT NULL
);
