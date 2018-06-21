from quart import Blueprint, request, current_app as app, jsonify

from ..auth import token_check
from ..snowflake import get_snowflake
from ..enums import ChannelType

bp = Blueprint('guilds', __name__)


@bp.route('', methods=['POST'])
async def create_guild():
    user_id = await token_check()
    j = await request.get_json()

    guild_id = get_snowflake()

    await app.db.execute(
        """
        INSERT INTO guilds (id, name, region, icon, owner_id,
            verification_level, default_message_notifications,
            explicit_content_filter)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """, guild_id, j['name'], j['region'], j['icon'], user_id,
        j.get('verification_level', 0),
        j.get('default_message_notifications', 0),
        j.get('explicit_content_filter', 0))

    await app.db.execute("""
    INSERT INTO members (user_id, guild_id)
    VALUES ($1, $2)
    """, user_id, guild_id)

    everyone_role_id = get_snowflake()

    await app.db.execute("""
    INSERT INTO roles (id, guild_id, name, position, permissions)
    VALUES ($1, $2, $3, $4, $5)
    """, everyone_role_id, guild_id, '@everyone', 0, 104324161)

    general_id = get_snowflake()

    await app.db.execute("""
    INSERT INTO channels (id, channel_type)
    VALUES ($1, $2)
    """, general_id, ChannelType.GUILD_TEXT)

    await app.db.execute("""
    INSERT INTO guild_channels (id, guild_id, name, position)
    VALUES ($1, $2, $3, $4)
    """, general_id, guild_id, 'general', 0)

    await app.db.execute("""
    INSERT INTO guild_text_channels (id)
    VALUES ($1)
    """, general_id)

    guild_json = await app.storage.get_guild(guild_id, user_id)
    guild_extra = await app.storage.get_guild_extra(guild_id, user_id, 250)

    return jsonify({**guild_json, **guild_extra})
