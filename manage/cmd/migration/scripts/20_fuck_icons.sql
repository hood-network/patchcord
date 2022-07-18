ALTER table users
DROP CONSTRAINT users_avatar_fkey,
DROP CONSTRAINT users_banner_fkey,
ADD CONSTRAINT users_avatar_fkey
   FOREIGN KEY (avatar) REFERENCES icons (hash)
   ON DELETE SET NULL ON UPDATE CASCADE,
ADD CONSTRAINT users_banner_fkey
   FOREIGN KEY (banner) REFERENCES icons (hash)
   ON DELETE SET NULL ON UPDATE CASCADE;

ALTER table members
DROP CONSTRAINT members_avatar_fkey,
DROP CONSTRAINT members_banner_fkey,
ADD CONSTRAINT members_avatar_fkey
   FOREIGN KEY (avatar) REFERENCES icons (hash)
   ON DELETE SET NULL ON UPDATE CASCADE,
ADD CONSTRAINT members_banner_fkey
   FOREIGN KEY (banner) REFERENCES icons (hash)
   ON DELETE SET NULL ON UPDATE CASCADE;

ALTER table group_dm_channels
DROP CONSTRAINT group_dm_channels_icon_fkey,
ADD CONSTRAINT group_dm_channels_icon_fkey
   FOREIGN KEY (icon) REFERENCES icons (hash)
   ON DELETE SET NULL ON UPDATE CASCADE;

ALTER table guild_emoji
DROP CONSTRAINT guild_emoji_image_fkey,
ADD CONSTRAINT guild_emoji_image_fkey
   FOREIGN KEY (image) REFERENCES icons (hash)
   ON DELETE CASCADE ON UPDATE CASCADE;

ALTER table guilds
ADD CONSTRAINT guilds_icon_fkey
   FOREIGN KEY (icon) REFERENCES icons (hash)
   ON DELETE SET NULL ON UPDATE CASCADE,
ADD CONSTRAINT guilds_splash_fkey
   FOREIGN KEY (splash) REFERENCES icons (hash)
   ON DELETE SET NULL ON UPDATE CASCADE,
ADD CONSTRAINT guilds_discovery_splash_fkey
   FOREIGN KEY (discovery_splash) REFERENCES icons (hash)
   ON DELETE SET NULL ON UPDATE CASCADE,
ADD CONSTRAINT guilds_banner_fkey
   FOREIGN KEY (banner) REFERENCES icons (hash)
   ON DELETE SET NULL ON UPDATE CASCADE;

UPDATE icons 
    SET hash = '#' || hash::text
    WHERE hash = hash;
