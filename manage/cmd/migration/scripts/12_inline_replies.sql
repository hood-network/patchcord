ALTER TABLE messages
    ADD COLUMN message_reference jsonb DEFAULT null,
    ADD COLUMN allowed_mentions jsonb DEFAULT null;
