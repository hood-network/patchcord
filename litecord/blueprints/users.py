from quart import Blueprint, jsonify, request, current_app as app
from asyncpg import UniqueViolationError

from ..auth import token_check
from ..errors import Forbidden, BadRequest

bp = Blueprint('user', __name__)


@bp.route('/@me', methods=['GET'])
async def get_me():
    """Get the current user's information."""
    user_id = await token_check()
    user = await app.storage.get_user(user_id, True)
    return jsonify(user)


@bp.route('/<int:user_id>', methods=['GET'])
async def get_other():
    """Get any user, given the user ID."""
    user_id = await token_check()

    bot = await app.db.fetchval("""
    SELECT bot FROM users
    WHERE users.id = $1
    """, user_id)

    if not bot:
        raise Forbidden('Only bots can use this endpoint')

    other = await app.storage.get_user(user_id)
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
