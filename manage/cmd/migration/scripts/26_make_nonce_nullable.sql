UPDATE messages
    SET nonce = NULL
    WHERE nonce = 0;

ALTER TABLE messages
    ALTER COLUMN nonce TYPE text;

ALTER TABLE messages
    ALTER COLUMN nonce set DEFAULT NULL;
