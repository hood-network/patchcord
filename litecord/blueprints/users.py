from quart import Blueprint, jsonify, request, current_app as app
from asyncpg import UniqueViolationError

from ..auth import token_check
from ..errors import Forbidden, BadRequest
from ..schemas import validate, USER_SETTINGS

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
async def leave_guild(guild_id):
    user_id = await token_check()

    await app.db.execute("""
    DELETE FROM members
    WHERE user_id = $1 AND guild_id = $2
    """, user_id, guild_id)

    # TODO: something to dispatch events to the users

    return '', 204


# @bp.route('/@me/connections', methods=['GET'])
async def get_connections():
    pass


# @bp.route('/@me/channels', methods=['GET'])
async def get_dms():
    pass


# @bp.route('/@me/channels', methods=['POST'])
async def start_dm():
    pass


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
