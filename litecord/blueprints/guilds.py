from quart import Blueprint, request, current_app as app, jsonify

from ..auth import token_check
from ..snowflake import get_snowflake
from ..enums import ChannelType
from ..errors import Forbidden, GuildNotFound, BadRequest
from ..schemas import (
    validate, GUILD_CREATE, GUILD_UPDATE, ROLE_CREATE, ROLE_UPDATE,
    ROLE_UPDATE_POSITION
)
from ..utils import dict_get
from .channels import channel_ack
from .checks import guild_check

bp = Blueprint('guilds', __name__)
DEFAULT_EVERYONE_PERMS = 104324161


async def guild_owner_check(user_id: int, guild_id: int):
    """Check if a user is the owner of the guild."""
    owner_id = await app.db.fetchval("""
    SELECT owner_id
    FROM guilds
    WHERE guilds.id = $1
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


async def create_role(guild_id, name: str, **kwargs):
    """Create a role in a guild."""
    new_role_id = get_snowflake()

    # TODO: use @everyone's perm number
    default_perms = dict_get(kwargs, 'default_perms', DEFAULT_EVERYONE_PERMS)

    max_pos = await app.db.fetchval("""
    SELECT MAX(position)
    FROM roles
    WHERE guild_id = $1
    """, guild_id)

    await app.db.execute(
        """
        INSERT INTO roles (id, guild_id, name, color,
            hoist, position, permissions, managed, mentionable)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """,
        new_role_id,
        guild_id,
        name,
        dict_get(kwargs, 'color', 0),
        dict_get(kwargs, 'hoist', False),

        # set position = 0 when there isn't any
        # other role (when we're creating the
        # @everyone role)
        max_pos + 1 if max_pos is not None else 0,
        int(dict_get(kwargs, 'permissions', default_perms)),
        False,
        dict_get(kwargs, 'mentionable', False)
    )

    role = await app.storage.get_role(new_role_id, guild_id)
    await app.dispatcher.dispatch_guild(
        guild_id, 'GUILD_ROLE_CREATE', {
            'guild_id': str(guild_id),
            'role': role,
        })

    return role


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


@bp.route('/<int:guild_id>/roles', methods=['POST'])
async def create_guild_role(guild_id: int):
    """Add a role to a guild"""
    user_id = await token_check()

    # TODO: use check_guild and MANAGE_ROLES permission
    await guild_owner_check(user_id, guild_id)

    # client can just send null
    j = validate(await request.get_json() or {}, ROLE_CREATE)

    role_name = j['name']
    j.pop('name')

    role = await create_role(guild_id, role_name, **j)

    return jsonify(role)


async def _role_update_dispatch(role_id: int, guild_id: int):
    """Dispatch a GUILD_ROLE_UPDATE with updated information on a role."""
    role = await app.storage.get_role(role_id, guild_id)

    await app.dispatcher.dispatch_guild(guild_id, 'GUILD_ROLE_UPDATE', {
        'guild_id': str(guild_id),
        'role': role,
    })

    return role


async def _role_pairs_update(guild_id: int, pairs: list):
    """Update the roles' positions.

    Dispatches GUILD_ROLE_UPDATE for all roles being updated.
    """
    for pair in pairs:
        pair_1, pair_2 = pair

        role_1, new_pos_1 = pair_1
        role_2, new_pos_2 = pair_2

        conn = await app.db.acquire()
        async with conn.transaction():
            # update happens in a transaction
            # so we don't fuck it up
            await conn.execute("""
            UPDATE roles
            SET position = $1
            WHERE roles.id = $2
            """, new_pos_1, role_1)

            await conn.execute("""
            UPDATE roles
            SET position = $1
            WHERE roles.id = $2
            """, new_pos_2, role_2)

        await app.db.release(conn)

        # the route fires multiple Guild Role Update.
        await _role_update_dispatch(role_1, guild_id)
        await _role_update_dispatch(role_2, guild_id)


@bp.route('/<int:guild_id>/roles', methods=['PATCH'])
async def update_guild_role_positions(guild_id):
    """Update the positions for a bunch of roles."""
    user_id = await token_check()

    # TODO: check MANAGE_ROLES
    await guild_owner_check(user_id, guild_id)

    raw_j = await request.get_json()

    # we need to do this hackiness because thats
    # cerberus for ya.
    j = validate({'roles': raw_j}, ROLE_UPDATE_POSITION)

    # extract the list out
    j = j['roles']
    print(j)

    all_roles = await app.storage.get_role_data(guild_id)

    # we'll have to calculate pairs of changing roles,
    # then do the changes, etc.
    roles_pos = {role['position']: int(role['id']) for role in all_roles}
    new_positions = {role['id']: role['position'] for role in j}

    # always ignore people trying to change the @everyone role
    # TODO: check if the user can even change the roles in the first place,
    #       preferrably when we have a proper perms system.
    try:
        new_positions.pop(guild_id)
    except KeyError:
        pass

    pairs = []

    # we want to find pairs of (role_1, new_position_1)
    # where new_position_1 is actually pointing to position_2 (for a role 2)
    # AND we have (role_2, new_position_2) in the list of new_positions.

    # I hope the explanation went through.

    for change in j:
        role_1, new_pos_1 = change['id'], change['position']

        # check current pairs
        # so we don't repeat a role
        flag = False

        for pair in pairs:
            if (role_1, new_pos_1) in pair:
                flag = True

        # skip if found
        if flag:
            continue

        # find a role that is in that new position
        role_2 = roles_pos.get(new_pos_1)

        # search role_2 in the new_positions list
        new_pos_2 = new_positions.get(role_2)

        # if we found it, add it to the pairs array.
        if new_pos_2:
            pairs.append(
                ((role_1, new_pos_1), (role_2, new_pos_2))
            )

    await _role_pairs_update(guild_id, pairs)

    # return the list of all roles back
    return jsonify(await app.storage.get_role_data(guild_id))


@bp.route('/<int:guild_id>/roles/<int:role_id>', methods=['PATCH'])
async def update_guild_role(guild_id, role_id):
    """Update a single role's information."""
    user_id = await token_check()

    # TODO: check MANAGE_ROLES
    await guild_owner_check(user_id, guild_id)

    j = validate(await request.get_json(), ROLE_UPDATE)

    # we only update ints on the db, not Permissions
    j['permissions'] = int(j['permissions'])

    for field in j:
        await app.db.execute(f"""
        UPDATE roles
        SET {field} = $1
        WHERE roles.id = $2 AND roles.guild_id = $3
        """, j[field], role_id, guild_id)

    role = await _role_update_dispatch(role_id, guild_id)
    return jsonify(role)


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
