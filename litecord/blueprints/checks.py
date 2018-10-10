from quart import current_app as app

from ..enums import ChannelType, GUILD_CHANS
from ..errors import GuildNotFound, ChannelNotFound


async def guild_check(user_id: int, guild_id: int):
    """Check if a user is in a guild."""
    joined_at = await app.db.execute("""
    SELECT joined_at
    FROM members
    WHERE user_id = $1 AND guild_id = $2
    """, user_id, guild_id)

    if not joined_at:
        raise GuildNotFound('guild not found')


async def channel_check(user_id, channel_id):
    """Check if the current user is authorized
    to read the channel's information."""
    chan_type = await app.storage.get_chan_type(channel_id)

    if chan_type is None:
        raise ChannelNotFound(f'channel type not found')

    ctype = ChannelType(chan_type)

    if ctype in GUILD_CHANS:
        guild_id = await app.db.fetchval("""
        SELECT guild_id
        FROM guild_channels
        WHERE guild_channels.id = $1
        """, channel_id)

        await guild_check(user_id, guild_id)
        return guild_id

    if ctype == ChannelType.DM:
        parties = await app.db.fetchrow("""
        SELECT party1_id, party2_id
        FROM dm_channels
        WHERE id = $1 AND (party1_id = $2 OR party2_id = $2)
        """, channel_id, user_id)

        parties = [parties['party1_id'], parties['party2_id']]

        # get the id of the other party
        parties.remove(user_id)
        return parties[0]
