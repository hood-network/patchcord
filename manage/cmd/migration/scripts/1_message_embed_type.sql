-- unused tables
DROP TABLE message_embeds;
DROP TABLE embeds;

ALTER TABLE messages
    ADD COLUMN embeds jsonb DEFAULT '[]'
