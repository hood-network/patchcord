-- update roles.color default to 0
ALTER TABLE roles
  ALTER COLUMN color SET DEFAULT 0;

-- update all existing guild default roles to
-- color=0
UPDATE roles
  SET color = 0
WHERE roles.id = roles.guild_id;
