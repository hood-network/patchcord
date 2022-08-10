ALTER TABLE guilds
    ADD COLUMN nsfw_level int DEFAULT 0;

ALTER TABLE users
    ADD COLUMN date_of_birth timestamp without time zone DEFAULT NULL;
