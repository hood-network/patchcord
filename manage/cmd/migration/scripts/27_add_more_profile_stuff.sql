ALTER TABLE members
    ADD COLUMN pronouns text DEFAULT '' NOT NULL;

ALTER TABLE users
    ADD COLUMN theme_colors integer[] DEFAULT NULL;
