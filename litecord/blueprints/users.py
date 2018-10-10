from quart import Blueprint, jsonify, request, current_app as app
from asyncpg import UniqueViolationError

from ..auth import token_check
from ..snowflake import get_snowflake
from ..errors import Forbidden, BadRequest
from ..schemas import validate, USER_SETTINGS, CREATE_DM, CREATE_GROUP_DM
from ..enums import ChannelType

from .guilds import guild_check

bp = Blueprint('user', __name__)


@bp.route('/@me', methods=['GET'])
async def get_me():
    """Get the current user's information."""
    user_id = await token_check()
    user = await app.storage.get_user(user_id, True)
    return jsonify(user)


@bp.route('/<int:target_id>', methods=['GET'])
async def get_other(target_id):
    """Get any user, given the user ID."""
    user_id = await token_check()

    bot = await app.db.fetchval("""
    SELECT bot FROM users
    WHERE users.id = $1
    """, user_id)

    if not bot:
        raise Forbidden('Only bots can use this endpoint')

    other = await app.storage.get_user(target_id)
    return jsonify(other)


@bp.route('/@me', methods=['PATCH'])
async def patch_me():
    """Patch the current user's information."""
    user_id = await token_check()
    j = await request.get_json()

    if not isinstance(j, dict):
        raise BadRequest('Invalid payload')

    user = await app.storage.get_user(user_id, True)

    if 'username' in j:
        try:
            await app.db.execute("""
            UPDATE users
            SET username = $1
            WHERE users.id = $2
            """, j['username'], user_id)
        except UniqueViolationError:
            raise BadRequest('Username already used.')

        user['username'] = j['username']

    return jsonify(user)


@bp.route('/@me/guilds', methods=['GET'])
async def get_me_guilds():
    """Get partial user guilds."""
    user_id = await token_check()
    guild_ids = await app.storage.get_user_guilds(user_id)

    partials = []

    for guild_id in guild_ids:
        partial = await app.db.fetchrow("""
        SELECT id::text, name, icon, owner_id
        FROM guilds
        WHERE guild_id = $1
        """, guild_id)

        # TODO: partial['permissions']
        partial['owner'] = partial['owner_id'] == user_id
        partial.pop('owner_id')

        partials.append(partial)

    return jsonify(partials)


@bp.route('/@me/guilds/<int:guild_id>', methods=['DELETE'])
async def leave_guild(guild_id: int):
    user_id = await token_check()
    await guild_check(user_id, guild_id)

    await app.db.execute("""
    DELETE FROM members
    WHERE user_id = $1 AND guild_id = $2
    """, user_id, guild_id)

    # first dispatch guild delete to the user,
    # then remove from the guild,
    # then tell the others that the member was removed
    await app.dispatcher.dispatch_user_guild(
        user_id, guild_id, 'GUILD_DELETE', {
            'id': str(guild_id),
            'unavailable': False,
        }
    )

    await app.dispatcher.unsub('guild', guild_id, user_id)

    await app.dispatcher.dispatch_guild('GUILD_MEMBER_REMOVE', {
        'guild_id': str(guild_id),
        'user': await app.storage.get_user(user_id)
    })

    return '', 204


# @bp.route('/@me/connections', methods=['GET'])
async def get_connections():
    pass


@bp.route('/@me/channels', methods=['GET'])
async def get_dms():
    user_id = await token_check()
    dms = await app.storage.get_dms(user_id)
    return jsonify(dms)


async def try_dm_state(user_id, dm_id):
    """Try insertin the user into the dm state
    for the given DM."""
    try:
        await app.db.execute("""
        INSERT INTO dm_channel_state (user_id, dm_id)
        VALUES ($1, $2)
        """, user_id, dm_id)
    except UniqueViolationError:
        # if already in state, ignore
        pass


async def create_dm(user_id, recipient_id):
    dm_id = get_snowflake()

    try:
        await app.db.execute("""
        INSERT INTO channels (id, channel_type)
        VALUES ($1, $2)
        """, dm_id, ChannelType.DM.value)

        await app.db.execute("""
        INSERT INTO dm_channels (id, party1_id, party2_id)
        VALUES ($1, $2, $3)
        """, dm_id, user_id, recipient_id)

        await try_dm_state(user_id, dm_id)

    except UniqueViolationError:
        # the dm already exists
        dm_id = await app.db.fetchval("""
        SELECT id
        FROM dm_channels
        WHERE (party1_id = $1 OR party2_id = $1) AND
              (party2_id = $2 OR party2_id = $2)
        """, user_id, recipient_id)

    dm = await app.storage.get_dm(dm_id, user_id)
    return jsonify(dm)


@bp.route('/@me/channels', methods=['POST'])
async def start_dm():
    """Create a DM with a user."""
    user_id = await token_check()
    j = validate(await request.get_json(), CREATE_DM)
    recipient_id = j['recipient_id']

    return await create_dm(user_id, recipient_id)


@bp.route('/<int:p_user_id>/channels', methods=['POST'])
async def create_group_dm(p_user_id: int):
    """Create a DM or a Group DM with user(s)."""
    user_id = await token_check()
    assert user_id == p_user_id

    j = validate(await request.get_json(), CREATE_GROUP_DM)
    recipients = j['recipients']

    if len(recipients) == 1:
        # its a group dm with 1 user... a dm!
        return await create_dm(user_id, int(recipients[0]))

    # TODO: group dms
    return 'group dms not implemented', 500


@bp.route('/@me/notes/<int:target_id>', methods=['PUT'])
async def put_note(target_id: int):
    """Put a note to a user."""
    user_id = await token_check()

    j = await request.get_json()
    note = str(j['note'])

    try:
        await app.db.execute("""
        INSERT INTO notes (user_id, target_id, note)
        VALUES ($1, $2, $3)
        """, user_id, target_id, note)
    except UniqueViolationError:
        await app.db.execute("""
        UPDATE notes
        SET note = $3
        WHERE user_id = $1 AND target_id = $2
        """, user_id, target_id, note)

    await app.dispatcher.dispatch_user(user_id, 'USER_NOTE_UPDATE', {
        'id': str(target_id),
        'note': note,
    })

    return '', 204


@bp.route('/@me/settings', methods=['GET'])
async def get_user_settings():
    """Get the current user's settings."""
    user_id = await token_check()
    settings = await app.storage.get_user_settings(user_id)
    return jsonify(settings)


@bp.route('/@me/settings', methods=['PATCH'])
async def patch_current_settings():
    user_id = await token_check()
    j = validate(await request.get_json(), USER_SETTINGS)

    for key in j:
        await app.db.execute(f"""
        UPDATE user_settings
        SET {key}=$1
        """, j[key])

    settings = await app.storage.get_user_settings(user_id)
    await app.dispatcher.dispatch_user(
        user_id, 'USER_SETTINGS_UPDATE', settings)
    return jsonify(settings)


@bp.route('/@me/consent', methods=['GET', 'POST'])
async def get_consent():
    """Always disable data collection.

    Also takes any data collection changes
    by the client and ignores them, as they
    will always be false.
    """
    return jsonify({
        'usage_statistics': {
            'consented': False,
        },
        'personalization': {
            'consented': False,
        }
    })


@bp.route('/@me/harvest', methods=['GET'])
async def get_harvest():
    """Dummy route"""
    return '', 204


@bp.route('/@me/activities/statistics/applications', methods=['GET'])
async def get_stats_applications():
    """Dummy route for info on gameplay time and such"""
    return jsonify([])


@bp.route('/@me/library', methods=['GET'])
async def get_library():
    """Probably related to Discord Store?"""
    return jsonify([])
