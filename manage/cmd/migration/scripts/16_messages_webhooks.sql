-- this is a tricky one. blame discord

-- first, remove all messages made by webhooks (safety check)
DELETE FROM messages WHERE author_id is null;

-- delete the column, removing the fkey. no connection anymore.
ALTER TABLE messages DROP COLUMN webhook_id;

-- add a message_webhook_info table. more on that in Storage._inject_author
CREATE TABLE IF NOT EXISTS message_webhook_info (
    message_id bigint REFERENCES messages (id) PRIMARY KEY,

    webhook_id bigint,
    name text DEFAULT '<invalid>',
    avatar text DEFAULT NULL
);

