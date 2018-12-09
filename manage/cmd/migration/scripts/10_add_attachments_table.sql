CREATE TABLE IF NOT EXISTS attachments (
    id bigint PRIMARY KEY,

    filename text NOT NULL,
    filesize integer,

    image boolean DEFAULT FALSE,

    -- only not null if image=true
    height integer DEFAULT NULL,
    width integer DEFAULT NULL
);

-- recreate the attachments table since
-- its been always error'ing since some migrations ago.
CREATE TABLE IF NOT EXISTS message_attachments (
    message_id bigint REFERENCES messages (id),
    attachment bigint REFERENCES attachments (id),
    PRIMARY KEY (message_id, attachment)
);

