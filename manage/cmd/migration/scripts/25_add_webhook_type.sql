ALTER TABLE webhooks
    ADD COLUMN type int NOT NULL DEFAULT 1,
    ADD COLUMN source_id bigint DEFAULT NULL;

ALTER TABLE messages
    ADD COLUMN sticker_ids jsonb DEFAULT '[]';
