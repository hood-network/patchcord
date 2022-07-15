UPDATE icons
    SET scope = 'user_avatar'
    WHERE scope = 'user';

UPDATE icons
    SET scope = 'guild_icon'
    WHERE scope = 'guild';

UPDATE icons
    SET scope = 'guild_splash'
    WHERE scope = 'splash';

UPDATE icons
    SET scope = 'guild_discovery_splash'
    WHERE scope = 'discovery_splash';

UPDATE icons
    SET scope = 'guild_banner'
    WHERE scope = 'banner';

UPDATE icons
    SET scope = 'channel_icon'
    WHERE scope = 'channel-icons';
