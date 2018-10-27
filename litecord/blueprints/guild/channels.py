from quart import Blueprint, request, current_app as app, jsonify

from litecord.blueprints.auth import token_check
from litecord.blueprints.checks import guild_check, guild_owner_check
from litecord.snowflake import get_snowflake
from litecord.errors import BadRequest
from litecord.enums import ChannelType
# from litecord.schemas import (
#     validate, CHAN_UPDATE_POSITION
# )


bp = Blueprint('guild_channels', __name__)


async def _specific_chan_create(channel_id, ctype, **kwargs):
    if ctype == ChannelType.GUILD_TEXT:
        await app.db.execute("""
        INSERT INTO guild_text_channels (id, topic)
        VALUES ($1, $2)
        """, channel_id, kwargs.get('topic', ''))
    elif ctype == ChannelType.GUILD_VOICE:
        await app.db.execute(
            """
            INSERT INTO guild_voice_channels (id, bitrate, user_limit)
            VALUES ($1, $2, $3)
            """,
            channel_id,
            kwargs.get('bitrate', 64),
            kwargs.get('user_limit', 0)
        )


async def create_guild_channel(guild_id: int, channel_id: int,
                               ctype: ChannelType, **kwargs):
    """Create a channel in a guild."""
    await app.db.execute("""
    INSERT INTO channels (id, channel_type)
    VALUES ($1, $2)
    """, channel_id, ctype.value)

    # calc new pos
    max_pos = await app.db.fetchval("""
    SELECT MAX(position)
    FROM guild_channels
    WHERE guild_id = $1
    """, guild_id)

    # account for the first channel in a guild too
    max_pos = max_pos or 0

    # all channels go to guild_channels
    await app.db.execute("""
    INSERT INTO guild_channels (id, guild_id, name, position)
    VALUES ($1, $2, $3, $4)
    """, channel_id, guild_id, kwargs['name'], max_pos + 1)

    # the rest of sql magic is dependant on the channel
    # we're creating (a text or voice or category),
    # so we use this function.
    await _specific_chan_create(channel_id, ctype, **kwargs)


@bp.route('/<int:guild>/channels', methods=['GET'])
async def get_guild_channels(guild_id):
    """Get the list of channels in a guild."""
    user_id = await token_check()
    await guild_check(user_id, guild_id)

    return jsonify(
        await app.storage.get_channel_data(guild_id))


@bp.route('/<int:guild_id>/channels', methods=['POST'])
async def create_channel(guild_id):
    """Create a channel in a guild."""
    user_id = await token_check()
    j = await request.get_json()

    # TODO: check permissions for MANAGE_CHANNELS
    await guild_check(user_id, guild_id)

    channel_type = j.get('type', ChannelType.GUILD_TEXT)
    channel_type = ChannelType(channel_type)

    if channel_type not in (ChannelType.GUILD_TEXT,
                            ChannelType.GUILD_VOICE):
        raise BadRequest('Invalid channel type')

    new_channel_id = get_snowflake()
    await create_guild_channel(
        guild_id, new_channel_id, channel_type, **j)

    chan = await app.storage.get_channel(new_channel_id)
    await app.dispatcher.dispatch_guild(
        guild_id, 'CHANNEL_CREATE', chan)
    return jsonify(chan)


@bp.route('/<int:guild_id>/channels', methods=['PATCH'])
async def modify_channel_pos(guild_id):
    user_id = await token_check()

    # TODO: check MANAGE_CHANNELS
    await guild_owner_check(user_id, guild_id)

    # TODO: this route
    # raw_j = await request.get_json()
    # j = validate({'channels': raw_j}, CHAN_UPDATE_POSITION)

    raise NotImplementedError
