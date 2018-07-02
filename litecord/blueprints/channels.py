from quart import Blueprint, request, current_app as app, jsonify

from ..auth import token_check
from ..snowflake import get_snowflake
from ..enums import ChannelType
from ..errors import Forbidden, BadRequest, MessageNotFound
from ..schemas import validate

from .guilds import guild_check

bp = Blueprint('channels', __name__)


async def channel_check(user_id, channel_id):
    ctype = await app.db.fetchval("""
    SELECT channel_type
    FROM channels
    WHERE channels.id = $1
    """, channel_id)

    if ctype in (ChannelType.GUILD_TEXT, ChannelType.GUILD_VOICE,
                 ChannelType.GUILD_CATEGORY):
        guild_id = await app.db.fetchval("""
        SELECT guild_id
        FROM guild_channels
        WHERE channel_id = $1
        """, channel_id)

        await guild_check(user_id, guild_id)


@bp.route('/<int:channel_id>', methods=['GET'])
async def get_channel(channel_id):
    user_id = await token_check()
    await channel_check(user_id, channel_id)
    return '', 204


@bp.route('/<int:channel_id>/messages', methods=['GET'])
async def get_messages(channel_id):
    user_id = await token_check()
    await channel_check(user_id, channel_id)

    # TODO: before, after, around keys

    await app.db.fetch(f"""
    SELECT *
    FROM messages
    WHERE channel_id = $1
    ORDER BY id ASC
    LIMIT 100
    """)


@bp.route('/<int:channel_id>/messages/<int:message_id>', methods=['GET'])
async def get_single_message(channel_id, message_id):
    user_id = await token_check()
    await channel_check(user_id, channel_id)

    # TODO: check READ_MESSAGE_HISTORY permissions

    message = await app.db.fetchrow("""
    SELECT *
    FROM messages
    WHERE channel_id = $1 AND messages.id = $2
    """, channel_id, message_id)

    if not message:
        raise MessageNotFound()


@bp.route('/<int:channel_id>/messages', methods=['POST'])
async def create_message(channel_id):
    user_id = await token_check()
    await channel_check(user_id, channel_id)

    # TODO: check SEND_MESSAGES permission
    # TODO: check SEND_TTS_MESSAGES
    # TODO: check connection to the gateway


    # TODO: parse payload, make schema
    # TODO: insert and dispatch message
