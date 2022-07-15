ALTER TABLE users
    ADD COLUMN banner text REFERENCES icons (hash) DEFAULT NULL;
ALTER TABLE members
    ADD COLUMN avatar text REFERENCES icons (hash) DEFAULT NULL,
    ADD COLUMN banner text REFERENCES icons (hash) DEFAULT NULL;
