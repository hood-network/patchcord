-- drop main primary key
-- since hash can now be nullable
ALTER TABLE icons DROP CONSTRAINT "icons_pkey";

-- remove not null from hash column
ALTER TABLE icons ALTER COLUMN hash DROP NOT NULL;

-- add new primary key, without hash
ALTER TABLE icons ADD CONSTRAINT icons_pkey PRIMARY KEY (scope, key);
