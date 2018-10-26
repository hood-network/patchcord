from quart import Blueprint, request, current_app as app, jsonify

from ..auth import token_check
from ..snowflake import get_snowflake
from ..enums import ChannelType
from ..errors import Forbidden, GuildNotFound, BadRequest
from ..schemas import validate, GUILD_CREATE, GUILD_UPDATE
from .channels import channel_ack
from .checks import guild_check

bp = Blueprint('guilds', __name__)
DEFAULT_EVERYONE_PERMS = 104324161


async def guild_owner_check(user_id: int, guild_id: int):
    """Check if a user is the owner of the guild."""
    owner_id = await app.db.fetchval("""
    SELECT owner_id
    FROM guilds
    WHERE guild_id = $1
    """, guild_id)

    if not owner_id:
        raise GuildNotFound()

    if user_id != owner_id:
        raise Forbidden('You are not the owner of the guild')


async def create_guild_settings(guild_id: int, user_id: int):
    """Create guild settings for the user
    joining the guild."""

    await app.db.execute("""
    INSERT INTO guild_settings (user_id, guild_id)
    VALUES ($1, $2)
    """, user_id, guild_id)

    m_notifs = await app.db.fetchval("""
    SELECT default_message_notifications
    FROM guilds
    WHERE id = $1
    """, guild_id)

    await app.db.execute("""
    UPDATE guild_settings
    SET message_notifications = $1
    WHERE user_id = $2 AND guild_id = $3
    """, m_notifs, user_id, guild_id)


async def add_member(guild_id: int, user_id: int):
    """Add a user to a guild."""
    await app.db.execute("""
    INSERT INTO members (user_id, guild_id)
    VALUES ($1, $2)
    """, user_id, guild_id)

    await create_guild_settings(guild_id, user_id)


async def guild_create_roles_prep(guild_id: int, roles: list):
    """Create roles in preparation in guild create."""
    # by reaching this point in the code that means
    # roles is not nullable, which means
    # roles has at least one element, so we can access safely.

    # the first member in the roles array
    # are patches to the @everyone role
    everyone_patches = roles[0]
    for field in everyone_patches:
        await app.db.execute(f"""
        UPDATE roles
        SET {field}={everyone_patches[field]}
        WHERE roles.id = $1
        """, guild_id)

    default_perms = (everyone_patches.get('permissions')
                     or DEFAULT_EVERYONE_PERMS)

    # from the 2nd and forward,
    # should be treated as new roles
    for role in roles[1:]:
        new_role_id = get_snowflake()

        await app.db.execute(
            """
            INSERT INTO roles (id, guild_id, name, color,
                hoist, position, permissions, managed, mentionable)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            new_role_id,
            guild_id,
            role['name'],
            role.get('color', 0),
            role.get('hoist', False),
            role.get('permissions', default_perms),
            False,
            role.get('mentionable', False)
        )


async def _specific_chan_create(channel_id, ctype, **kwargs):
    if ctype == ChannelType.GUILD_TEXT:
        await app.db.execute("""
        INSERT INTO guild_text_channels (id, topic)
        VALUES ($1)
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

    # all channels go to guild_channels
    await app.db.execute("""
    INSERT INTO guild_channels (id, guild_id, name, position)
    VALUES ($1, $2, $3, $4)
    """, channel_id, guild_id, kwargs['name'], max_pos + 1)

    # the rest of sql magic is dependant on the channel
    # we're creating (a text or voice or category),
    # so we use this function.
    await _specific_chan_create(channel_id, ctype, **kwargs)


async def guild_create_channels_prep(guild_id: int, channels: list):
    """Create channels pre-guild create"""
    for channel_raw in channels:
        channel_id = get_snowflake()
        ctype = ChannelType(channel_raw['type'])

        await create_guild_channel(guild_id, channel_id, ctype)


@bp.route('', methods=['POST'])
async def create_guild():
    """Create a new guild, assigning
    the user creating it as the owner and
    making them join."""
    user_id = await token_check()
    j = validate(await request.get_json(), GUILD_CREATE)

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

    await add_member(guild_id, user_id)

    # create the default @everyone role (everyone has it by default,
    # so we don't insert that in the table)
    await app.db.execute("""
    INSERT INTO roles (id, guild_id, name, position, permissions)
    VALUES ($1, $2, $3, $4, $5)
    """, guild_id, guild_id, '@everyone', 0, DEFAULT_EVERYONE_PERMS)

    # create a single #general channel.
    general_id = get_snowflake()

    await create_guild_channel(
        guild_id, general_id, ChannelType.GUILD_TEXT,
        name='general')

    if j.get('roles'):
        await guild_create_roles_prep(guild_id, j['roles'])

    if j.get('channels'):
        await guild_create_channels_prep(guild_id, j['channels'])

    guild_total = await app.storage.get_guild_full(guild_id, user_id, 250)

    await app.dispatcher.sub('guild', guild_id, user_id)
    await app.dispatcher.dispatch_guild(guild_id, 'GUILD_CREATE', guild_total)
    return jsonify(guild_total)


@bp.route('/<int:guild_id>', methods=['GET'])
async def get_guild(guild_id):
    """Get a single guilds' information."""
    user_id = await token_check()
    await guild_check(user_id, guild_id)

    return jsonify(
        await app.storage.get_guild_full(guild_id, user_id, 250)
    )


@bp.route('/<int:guild_id>', methods=['UPDATE'])
async def update_guild(guild_id):
    user_id = await token_check()
    await guild_check(user_id, guild_id)
    j = validate(await request.get_json(), GUILD_UPDATE)

    # TODO: check MANAGE_GUILD

    if 'owner_id' in j:
        await guild_owner_check(user_id, guild_id)

        await app.db.execute("""
        UPDATE guilds
        SET owner_id = $1
        WHERE guild_id = $2
        """, int(j['owner_id']), guild_id)

    if 'name' in j:
        await app.db.execute("""
        UPDATE guilds
        SET name = $1
        WHERE guild_id = $2
        """, j['name'], guild_id)

    if 'region' in j:
        await app.db.execute("""
        UPDATE guilds
        SET region = $1
        WHERE guild_id = $2
        """, j['region'], guild_id)

    fields = ['verification_level', 'default_message_notifications',
              'explicit_content_filter', 'afk_timeout']

    for field in [f for f in fields if f in j]:
        await app.db.execute("""
        UPDATE guilds
        SET {field} = $1
        WHERE guild_id = $2
        """, j[field], guild_id)

    channel_fields = ['afk_channel_id', 'system_channel_id']
    for field in [f for f in channel_fields if f in j]:
        # TODO: check channel link to guild

        await app.db.execute("""
        UPDATE guilds
        SET {field} = $1
        WHERE guild_id = $2
        """, j[field], guild_id)

    guild = await app.storage.get_guild_full(
        guild_id, user_id
    )

    await app.dispatcher.dispatch_guild(
        guild_id, 'GUILD_UPDATE', guild)

    return jsonify(guild)


@bp.route('/<int:guild_id>', methods=['DELETE'])
async def delete_guild(guild_id):
    """Delete a guild."""
    user_id = await token_check()
    await guild_owner_check(user_id, guild_id)

    await app.db.execute("""
    DELETE FROM guilds
    WHERE guilds.id = $1
    """, guild_id)

    await app.dispatcher.dispatch_guild(guild_id, 'GUILD_DELETE', {
        'id': guild_id,
        'unavailable': False,
    })

    # remove from the dispatcher so nobody
    # becomes the little memer that tries to fuck up with
    # everybody's gateway
    await app.dispatcher.remove('guild', guild_id)

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

    channel_type = j.get('type', ChannelType.GUILD_TEXT)
    channel_type = ChannelType(channel_type)

    if channel_type not in (ChannelType.GUILD_TEXT,
                            ChannelType.GUILD_VOICE):
        raise BadRequest('Invalid channel type')

    new_channel_id = get_snowflake()
    await create_guild_channel(guild_id, new_channel_id, channel_type,)

    chan = await app.storage.get_channel(new_channel_id)
    await app.dispatcher.dispatch_guild(
        guild_id, 'CHANNEL_CREATE', chan)
    return jsonify(chan)


@bp.route('/<int:guild_id>/channels', methods=['PATCH'])
async def modify_channel_pos(guild_id):
    user_id = await token_check()
    await guild_check(user_id, guild_id)
    await request.get_json()

    # TODO: this route

    raise NotImplementedError


@bp.route('/<int:guild_id>/members/<int:member_id>', methods=['GET'])
async def get_guild_member(guild_id, member_id):
    """Get a member's information in a guild."""
    user_id = await token_check()
    await guild_check(user_id, guild_id)
    member = await app.storage.get_single_member(guild_id, member_id)
    return jsonify(member)


@bp.route('/<int:guild_id>/members', methods=['GET'])
async def get_members(guild_id):
    """Get members inside a guild."""
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


@bp.route('/<int:guild_id>/members/<int:member_id>', methods=['PATCH'])
async def modify_guild_member(guild_id, member_id):
    """Modify a members' information in a guild."""
    j = await request.get_json()

    if 'nick' in j:
        # TODO: check MANAGE_NICKNAMES

        await app.db.execute("""
        UPDATE members
        SET nickname = $1
        WHERE user_id = $2 AND guild_id = $3
        """, j['nick'], member_id, guild_id)

    if 'mute' in j:
        # TODO: check MUTE_MEMBERS

        await app.db.execute("""
        UPDATE members
        SET muted = $1
        WHERE user_id = $2 AND guild_id = $3
        """, j['mute'], member_id, guild_id)

    if 'deaf' in j:
        # TODO: check DEAFEN_MEMBERS

        await app.db.execute("""
        UPDATE members
        SET deafened = $1
        WHERE user_id = $2 AND guild_id = $3
        """, j['deaf'], member_id, guild_id)

    if 'channel_id' in j:
        # TODO: check MOVE_MEMBERS
        # TODO: change the member's voice channel
        pass

    member = await app.storage.get_member_data_one(guild_id, member_id)
    member.pop('joined_at')

    await app.dispatcher.dispatch_guild(guild_id, 'GUILD_MEMBER_UPDATE', {**{
        'guild_id': str(guild_id)
    }, **member})

    return '', 204


@bp.route('/<int:guild_id>/members/@me/nick', methods=['PATCH'])
async def update_nickname(guild_id):
    """Update a member's nickname in a guild."""
    user_id = await token_check()
    await guild_check(user_id, guild_id)

    j = await request.get_json()

    await app.db.execute("""
    UPDATE members
    SET nickname = $1
    WHERE user_id = $2 AND guild_id = $3
    """, j['nick'], user_id, guild_id)

    member = await app.storage.get_member_data_one(guild_id, user_id)
    member.pop('joined_at')

    await app.dispatcher.dispatch_guild(guild_id, 'GUILD_MEMBER_UPDATE', {**{
        'guild_id': str(guild_id)
    }, **member})

    return j['nick']


async def remove_member(guild_id: int, member_id: int):
    """Do common tasks related to deleting a member from the guild,
    such as dispatching GUILD_DELETE and GUILD_MEMBER_REMOVE."""

    await app.db.execute("""
    DELETE FROM members
    WHERE guild_id = $1 AND user_id = $2
    """, guild_id, member_id)

    await app.dispatcher.dispatch_user(member_id, 'GUILD_DELETE', {
        'guild_id': guild_id,
        'unavailable': False,
    })

    await app.dispatcher.unsub('guild', guild_id, member_id)

    await app.dispatcher.dispatch_guild(guild_id, 'GUILD_MEMBER_REMOVE', {
        'guild': guild_id,
        'user': await app.storage.get_user(member_id),
    })


@bp.route('/<int:guild_id>/members/<int:member_id>', methods=['DELETE'])
async def kick_member(guild_id, member_id):
    """Remove a member from a guild."""
    user_id = await token_check()

    # TODO: check KICK_MEMBERS permission
    await guild_owner_check(user_id, guild_id)
    await remove_member(guild_id, member_id)
    return '', 204


@bp.route('/<int:guild_id>/bans', methods=['GET'])
async def get_bans(guild_id):
    user_id = await token_check()

    # TODO: check BAN_MEMBERS permission
    await guild_owner_check(user_id, guild_id)

    bans = await app.db.fetch("""
    SELECT user_id, reason
    FROM bans
    WHERE bans.guild_id = $1
    """, guild_id)

    res = []

    for ban in bans:
        res.append({
            'reason': ban['reason'],
            'user': await app.storage.get_user(ban['user_id'])
        })

    return jsonify(res)


@bp.route('/<int:guild_id>/bans/<int:member_id>', methods=['PUT'])
async def create_ban(guild_id, member_id):
    user_id = await token_check()

    # TODO: check BAN_MEMBERS permission
    await guild_owner_check(user_id, guild_id)

    j = await request.get_json()

    await app.db.execute("""
    INSERT INTO bans (guild_id, user_id, reason)
    VALUES ($1, $2, $3)
    """, guild_id, member_id, j.get('reason', ''))

    await remove_member(guild_id, member_id)

    await app.dispatcher.dispatch_guild(guild_id, 'GUILD_BAN_ADD', {**{
        'guild': guild_id,
    }, **(await app.storage.get_user(member_id))})

    return '', 204


@bp.route('/<int:guild_id>/messages/search')
async def search_messages(guild_id):
    """Search messages in a guild.

    This is an undocumented route.
    """
    user_id = await token_check()
    await guild_check(user_id, guild_id)

    # TODO: implement route

    return jsonify({
        'total_results': 0,
        'messages': [],
        'analytics_id': 'ass',
    })


@bp.route('/<int:guild_id>/ack', methods=['POST'])
async def ack_guild(guild_id):
    """ACKnowledge all messages in the guild."""
    user_id = await token_check()
    await guild_check(user_id, guild_id)

    chan_ids = await app.storage.get_channel_ids(guild_id)

    for chan_id in chan_ids:
        await channel_ack(user_id, guild_id, chan_id)

    return '', 204
