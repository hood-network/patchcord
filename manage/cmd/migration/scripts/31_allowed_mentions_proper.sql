ALTER TABLE messages
    DROP COLUMN allowed_mentions;

ALTER TABLE messages
    ADD COLUMN mentions bigint[] NOT NULL DEFAULT array[]::bigint[];

ALTER TABLE messages
    ADD COLUMN mention_roles bigint[] NOT NULL DEFAULT array[]::bigint[];
