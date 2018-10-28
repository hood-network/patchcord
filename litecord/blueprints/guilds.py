from quart import Blueprint, request, current_app as app, jsonify

from litecord.blueprints.guild.channels import create_guild_channel
from litecord.blueprints.guild.roles import (
    create_role, DEFAULT_EVERYONE_PERMS
)

from ..auth import token_check
from ..snowflake import get_snowflake
from ..enums import ChannelType
from ..schemas import (
    validate, GUILD_CREATE, GUILD_UPDATE
)
from ..utils import dict_get
from .channels import channel_ack
from .checks import guild_check, guild_owner_check


bp = Blueprint('guilds', __name__)


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
        await create_role(
            guild_id, role['name'], default_perms=default_perms, **role
        )


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

    # we also don't use create_role because the id of the role
    # is the same as the id of the guild, and create_role
    # generates a new snowflake.
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

    # TODO: check MANAGE_GUILD
    await guild_check(user_id, guild_id)
    j = validate(await request.get_json(), GUILD_UPDATE)

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
        'guild_id': str(guild_id),
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

    await app.dispatcher.dispatch_guild(guild_id, 'GUILD_BAN_ADD', {
        'guild_id': str(guild_id),
        'user': await app.storage.get_user(member_id)
    })

    return '', 204


@bp.route('/<int:guild_id>/bans/<int:banned_id>', methods=['DELETE'])
async def remove_ban(guild_id, banned_id):
    user_id = await token_check()

    # TODO: check BAN_MEMBERS permission
    await guild_owner_check(guild_id, user_id)

    res = await app.db.execute("""
    DELETE FROM bans
    WHERE guild_id = $1 AND user_id = $@
    """, guild_id, banned_id)

    # we don't really need to dispatch GUILD_BAN_REMOVE
    # when no bans were actually removed.
    if res == 'DELETE 0':
        return '', 204

    await app.dispatcher.dispatch_guild(guild_id, 'GUILD_BAN_REMOVE', {
        'guild_id': str(guild_id),
        'user': await app.storage.get_user(banned_id)
    })

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
