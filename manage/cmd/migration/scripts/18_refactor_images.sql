UPDATE icons
SET scope = 'user_avatar'
WHERE scope = 'avatar',
SET scope = 'user_banner'
WHERE scope = 'banner',
SET scope = 'guild_icon'
WHERE scope = 'guild',
SET scope = 'guild_splash'
WHERE scope = 'splash',
SET scope = 'guild_discovery_splash'
WHERE scope = 'discovery_splash',
SET scope = 'guild_banner'
WHERE scope = 'banner',
SET scope = 'channel_icon'
WHERE scope = 'channel-icons';
