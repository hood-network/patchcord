"""

Litecord
Copyright (C) 2018-2019  Luna Mendes

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""

from quart import Blueprint, request, current_app as app, jsonify

from litecord.blueprints.guild.channels import create_guild_channel
from litecord.blueprints.guild.roles import (
    create_role, DEFAULT_EVERYONE_PERMS
)

from ..auth import token_check
from ..snowflake import get_snowflake
from ..enums import ChannelType
from ..schemas import (
    validate, GUILD_CREATE, GUILD_UPDATE, SEARCH_CHANNEL
)
from .channels import channel_ack
from .checks import guild_check, guild_owner_check, guild_perm_check

from litecord.errors import BadRequest


bp = Blueprint('guilds', __name__)


async def create_guild_settings(guild_id: int, user_id: int):
    """Create guild settings for the user
    joining the guild."""

    # new guild_settings are based off the currently
    # set guild settings (for the guild)
    m_notifs = await app.db.fetchval("""
    SELECT default_message_notifications
    FROM guilds
    WHERE id = $1
    """, guild_id)

    await app.db.execute("""
    INSERT INTO guild_settings
        (user_id, guild_id, message_notifications)
    VALUES
        ($1, $2, $3)
    """, user_id, guild_id, m_notifs)


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


async def put_guild_icon(guild_id: int, icon: str):
    """Insert a guild icon on the icon database."""
    if icon and icon.startswith('data'):
        encoded = icon
    else:
        encoded = (f'data:image/jpeg;base64,{icon}'
                   if icon
                   else None)

    return await app.icons.put(
        'guild', guild_id, encoded, size=(128, 128), always_icon=True)


@bp.route('', methods=['POST'])
async def create_guild():
    """Create a new guild, assigning
    the user creating it as the owner and
    making them join."""
    user_id = await token_check()
    j = validate(await request.get_json(), GUILD_CREATE)

    guild_id = get_snowflake()

    image = await put_guild_icon(guild_id, j['icon'])

    await app.db.execute(
        """
        INSERT INTO guilds (id, name, region, icon, owner_id,
            verification_level, default_message_notifications,
            explicit_content_filter)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """, guild_id, j['name'], j['region'], image.icon_hash, user_id,
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

    # add the @everyone role to the guild creator
    await app.db.execute("""
    INSERT INTO member_roles (user_id, guild_id, role_id)
    VALUES ($1, $2, $3)
    """, user_id, guild_id, guild_id)

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


@bp.route('/<int:guild_id>', methods=['PATCH'])
async def _update_guild(guild_id):
    user_id = await token_check()

    await guild_check(user_id, guild_id)
    await guild_perm_check(user_id, guild_id, 'manage_guild')
    j = validate(await request.get_json(), GUILD_UPDATE)

    if 'owner_id' in j:
        await guild_owner_check(user_id, guild_id)

        await app.db.execute("""
        UPDATE guilds
        SET owner_id = $1
        WHERE id = $2
        """, int(j['owner_id']), guild_id)

    if 'name' in j:
        await app.db.execute("""
        UPDATE guilds
        SET name = $1
        WHERE id = $2
        """, j['name'], guild_id)

    if 'region' in j:
        await app.db.execute("""
        UPDATE guilds
        SET region = $1
        WHERE id = $2
        """, j['region'], guild_id)

    if 'icon' in j:
        # delete old
        new_icon = await app.icons.update(
            'guild', guild_id, j['icon'], always_icon=True
        )

        await app.db.execute("""
        UPDATE guilds
        SET icon = $1
        WHERE id = $2
        """, new_icon.icon_hash, guild_id)

    fields = ['verification_level', 'default_message_notifications',
              'explicit_content_filter', 'afk_timeout']

    for field in [f for f in fields if f in j]:
        await app.db.execute(f"""
        UPDATE guilds
        SET {field} = $1
        WHERE id = $2
        """, j[field], guild_id)

    channel_fields = ['afk_channel_id', 'system_channel_id']
    for field in [f for f in channel_fields if f in j]:
        chan = await app.storage.get_channel(int(j[field]))

        if chan is None:
            raise BadRequest('invalid channel id')

        if chan['guild_id'] != str(guild_id):
            raise BadRequest('channel id not linked to guild')

        await app.db.execute(f"""
        UPDATE guilds
        SET {field} = $1
        WHERE id = $2
        """, j[field], guild_id)

    guild = await app.storage.get_guild_full(
        guild_id, user_id
    )

    await app.dispatcher.dispatch_guild(
        guild_id, 'GUILD_UPDATE', guild)

    return jsonify(guild)


@bp.route('/<int:guild_id>', methods=['DELETE'])
@bp.route('/<int:guild_id>/delete', methods=['POST']) # this one is not actually documented, but it's used by Discord client
async def delete_guild(guild_id):
    """Delete a guild."""
    user_id = await token_check()
    await guild_owner_check(user_id, guild_id)

    await app.db.execute("""
    DELETE FROM guilds
    WHERE guilds.id = $1
    """, guild_id)

    # Discord's client expects IDs being string
    await app.dispatcher.dispatch('guild', guild_id, 'GUILD_DELETE', {
        'guild_id': str(guild_id),
        'id': str(guild_id),
        # 'unavailable': False,
    })

    # remove from the dispatcher so nobody
    # becomes the little memer that tries to fuck up with
    # everybody's gateway
    await app.dispatcher.remove('guild', guild_id)

    return '', 204


@bp.route('/<int:guild_id>/messages/search', methods=['GET'])
async def search_messages(guild_id):
    """Search messages in a guild.

    This is an undocumented route.
    """
    user_id = await token_check()
    await guild_check(user_id, guild_id)

    j = validate(dict(request.args), SEARCH_CHANNEL)

    # main message ids
    # TODO: filter only channels where user can
    # read messages to prevent leaking

    rows = await app.db.fetch(f"""
    SELECT messages.id,
        COUNT(*) OVER() as total_results
    FROM messages
    WHERE guild_id = $1
      AND messages.content LIKE '%'||$2||'%'
    ORDER BY messages.id DESC
    LIMIT 50
    OFFSET $3
    """, guild_id, j['content'], j['offset'])

    results = 0 if not rows else rows[0]['total_results']
    main_messages = [r['id'] for r in rows]

    # fetch contexts for each message
    # (2 messages before, 2 messages after).

    # TODO: actual contexts
    res = []

    for message_id in main_messages:
        msg = await app.storage.get_message(message_id)
        msg['hit'] = True
        res.append([msg])

    return jsonify({
        'total_results': results,
        'messages': res,
        'analytics_id': '',
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
