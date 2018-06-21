from quart import Blueprint, request, current_app as app, jsonify

from ..auth import token_check
from ..snowflake import get_snowflake
from ..enums import ChannelType
from ..errors import Forbidden, GuildNotFound, BadRequest

bp = Blueprint('guilds', __name__)


async def guild_check(user_id: int, guild_id: int):
    """Check if a user is in a guild."""
    joined_at = await app.db.execute("""
    SELECT joined_at
    FROM members
    WHERE user_id = $1 AND guild_id = $2
    """, user_id, guild_id)

    if not joined_at:
        raise GuildNotFound()


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


@bp.route('/<int:guild_id>', methods=['GET'])
async def get_guild(guild_id):
    user_id = await token_check()
    gj = await app.storage.get_guild(guild_id, user_id)
    gj_extra = await app.storage.get_guild_extra(guild_id, user_id, 250)

    return jsonify({**gj, **gj_extra})


@bp.route('/<int:guild_id>', methods=['DELETE'])
async def delete_guild(guild_id):
    user_id = await token_check()

    owner_id = await app.db.fetchval("""
    SELECT owner_id
    FROM guilds
    WHERE guild_id = $1
    """, guild_id)

    if not owner_id:
        raise GuildNotFound()

    if user_id != owner_id:
        raise Forbidden('You are not the owner of the guild')

    # TODO: delete guild, fire GUILD_DELETE to guild

    return '', 204


@bp.route('/<int:guild>/channels', methods=['GET'])
async def get_guild_channels(guild_id):
    user_id = await token_check()
    await guild_check(user_id, guild_id)

    channels = await app.storage.get_channel_data(guild_id)
    return jsonify(channels)


@bp.route('/<int:guild_id>/channels', methods=['POST'])
async def create_channel(guild_id):
    user_id = await token_check()
    j = await request.get_json()

    # TODO: check permissions for MANAGE_CHANNELS
    await guild_check(user_id, guild_id)

    new_channel_id = get_snowflake()
    channel_type = j.get('type', ChannelType.GUILD_TEXT)

    if channel_type not in (ChannelType.GUILD_TEXT,
                            ChannelType.GUILD_VOICE):
        raise BadRequest('Invalid channel type')

    await app.db.execute("""
    INSERT INTO channels (id, channel_type)
    VALUES ($1, $2)
    """, new_channel_id, channel_type)

    max_pos = await app.db.fetch("""
    SELECT MAX(position)
    FROM guild_channels
    WHERE guild_id = $1
    """, guild_id)

    channel = {
        'id': str(new_channel_id),
        'type': channel_type,
        'guild_id': str(guild_id),
        'position': max_pos + 1,
        'permission_overwrites': [],
        'nsfw': False,
        'name': j['name'],
    }

    if channel_type == ChannelType.GUILD_TEXT:
        await app.db.execute("""
        INSERT INTO guild_channels (id, guild_id, name, position)
        VALUES ($1, $2, $3, $4)
        """, new_channel_id, guild_id, j['name'], max_pos + 1)

        await app.db.execute("""
        INSERT INTO guild_text_channels (id)
        VALUES ($1)
        """, new_channel_id)

        channel['topic'] = None
    elif channel_type == ChannelType.GUILD_VOICE:
        channel['user_limit'] = 0
        channel['bitrate'] = 64

        raise NotImplementedError()

    # TODO: fire Channel Create event

    return jsonify(channel)


@bp.route('/<int:guild_id>/members/<int:member_id>', methods=['GET'])
async def get_guild_member(guild_id, member_id):
    user_id = await token_check()
    await guild_check(user_id, guild_id)

    member = await app.storage.get_single_member(guild_id, member_id)
    return jsonify(member)


@bp.route('/<int:guild_id>/members', methods=['GET'])
async def get_members(guild_id):
    user_id = await token_check()
    await guild_check(user_id, guild_id)

    j = await request.get_json()

    limit, after = int(j.get('limit', 1)), j.get('after', 0)

    if limit < 1 or limit > 1000:
        raise BadRequest('limit not in 1-1000 range')

    user_ids = await app.db.fetch(f"""
    SELECT user_id
    WHERE guild_id = $1, user_id > $2
    LIMIT {limit}
    ORDER BY user_id ASC
    """, guild_id, after)

    user_ids = [r[0] for r in user_ids]
    members = await app.storage.get_member_multi(guild_id, user_ids)
    return jsonify(members)


@bp.route('/<int:guild_id>/members/@me/nick', methods=['PATCH'])
async def update_nickname(guild_id):
    user_id = await token_check()
    await guild_check(user_id, guild_id)

    j = await request.get_json()

    await app.db.execute("""
    UPDATE members
    SET nickname = $1
    WHERE user_id = $2 AND guild_id = $3
    """, j['nick'], user_id, guild_id)

    # TODO: fire guild member update event

    return j['nick']
