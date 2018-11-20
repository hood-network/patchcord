import random

from asyncpg import UniqueViolationError
from quart import Blueprint, jsonify, request, current_app as app

from ..auth import token_check
from ..errors import Forbidden, BadRequest
from ..schemas import validate, USER_UPDATE

from .guilds import guild_check
from .auth import check_password
from litecord.auth import hash_data, check_username_usage
from litecord.blueprints.guild.mod import remove_member

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


async def _try_reroll(user_id, preferred_username: str = None):
    for _ in range(10):
        reroll = str(random.randint(1, 9999))

        if preferred_username:
            existing_uid = await app.db.fetchrow("""
            SELECT user_id
            FROM users
            WHERE preferred_username = $1 AND discriminator = $2
            """, preferred_username, reroll)

            if not existing_uid:
                return reroll

            continue

        try:
            await app.db.execute("""
            UPDATE users
            SET discriminator = $1
            WHERE users.id = $2
            """, reroll, user_id)

            return reroll
        except UniqueViolationError:
            continue

    return


async def _try_username_patch(user_id, new_username: str) -> str:
    await check_username_usage(new_username)
    discrim = None

    try:
        await app.db.execute("""
        UPDATE users
        SET username = $1
        WHERE users.id = $2
        """, new_username, user_id)

        return await app.db.fetchval("""
        SELECT discriminator
        FROM users
        WHERE users.id = $1
        """, user_id)
    except UniqueViolationError:
        discrim = await _try_reroll(user_id, new_username)

        if not discrim:
            raise BadRequest('Unable to change username', {
                'username': 'Too many people are with this username.'
            })

        await app.db.execute("""
        UPDATE users
        SET username = $1, discriminator = $2
        WHERE users.id = $3
        """, new_username, discrim, user_id)

    return discrim


async def _try_discrim_patch(user_id, new_discrim: str):
    try:
        await app.db.execute("""
        UPDATE users
        SET discriminator = $1
        WHERE id = $2
        """, new_discrim, user_id)
    except UniqueViolationError:
        raise BadRequest('Invalid discriminator', {
            'discriminator': 'Someone already used this discriminator.'
        })


def to_update(j: dict, user: dict, field: str):
    return field in j and j[field] and j[field] != user[field]


async def _check_pass(j, user):
    if not j['password']:
        raise BadRequest('password required', {
            'password': 'password required'
        })

    phash = user['password_hash']

    if not await check_password(phash, j['password']):
        raise BadRequest('password incorrect', {
            'password': 'password does not match.'
        })


@bp.route('/@me', methods=['PATCH'])
async def patch_me():
    """Patch the current user's information."""
    user_id = await token_check()

    j = validate(await request.get_json(), USER_UPDATE)
    user = await app.storage.get_user(user_id, True)

    user['password_hash'] = await app.db.fetchval("""
    SELECT password_hash
    FROM users
    WHERE id = $1
    """, user_id)

    if to_update(j, user, 'username'):
        # this will take care of regenning a new discriminator
        discrim = await _try_username_patch(user_id, j['username'])
        user['username'] = j['username']
        user['discriminator'] = discrim

    if to_update(j, user, 'discriminator'):
        # the API treats discriminators as integers,
        # but I work with strings on the database.
        new_discrim = str(j['discriminator'])

        await _try_discrim_patch(user_id, new_discrim)
        user['discriminator'] = new_discrim

    if to_update(j, user, 'email'):
        await _check_pass(j, user)

        # TODO: reverify the new email?
        await app.db.execute("""
        UPDATE users
        SET email = $1
        WHERE id = $2
        """, j['email'], user_id)
        user['email'] = j['email']

    # only update if values are different
    # from what the user gave.

    # this will return false if the client
    # sends j['avatar'] as the user's
    # original avatar hash, as they're the
    # same.

    # IconManager.update will take care of validating
    # the value once put()-ing
    if to_update(j, user, 'avatar'):
        new_icon = await app.icons.update(
            'user', user_id, j['avatar'], size=(128, 128))

        await app.db.execute("""
        UPDATE users
        SET avatar = $1
        WHERE id = $2
        """, new_icon.icon_hash, user_id)

    if 'new_password' in j and j['new_password']:
        await _check_pass(j, user)

        new_hash = await hash_data(j['new_password'])

        await app.db.execute("""
        UPDATE users
        SET password_hash = $1
        WHERE id = $2
        """, new_hash, user_id)

    user.pop('password_hash')

    public_user = await app.storage.get_user(user_id)
    private_user = await app.storage.get_user(user_id, secure=True)
    session_ids = []

    # by using dispatch_with_filter
    # we're guaranteeing all shards will get
    # a USER_UPDATE once and not any others.
    session_ids.extend(
        await app.dispatcher.dispatch_user(
            user_id, 'USER_UPDATE', private_user)
    )

    guild_ids = await app.user_storage.get_user_guilds(user_id)
    friend_ids = await app.user_storage.get_friend_ids(user_id)

    session_ids.extend(
        await app.dispatcher.dispatch_many_filter_list(
            'guild', guild_ids, session_ids,
            'USER_UPDATE', public_user
        )
    )

    session_ids.extend(
        await app.dispatcher.dispatch_many_filter_list(
            'friend', friend_ids, session_ids,
            'USER_UPDATE', public_user
        )
    )

    await app.dispatcher.dispatch_many(
        'lazy_guild', guild_ids, 'update_user', user_id
    )

    return jsonify(private_user)


@bp.route('/@me/guilds', methods=['GET'])
async def get_me_guilds():
    """Get partial user guilds."""
    user_id = await token_check()
    guild_ids = await app.user_storage.get_user_guilds(user_id)

    partials = []

    for guild_id in guild_ids:
        partial = await app.db.fetchrow("""
        SELECT id::text, name, icon, owner_id
        FROM guilds
        WHERE guilds.id = $1
        """, guild_id)

        partial = dict(partial)

        # TODO: partial['permissions']
        partial['owner'] = partial['owner_id'] == user_id
        partial.pop('owner_id')

        partials.append(partial)

    return jsonify(partials)


@bp.route('/@me/guilds/<int:guild_id>', methods=['DELETE'])
async def leave_guild(guild_id: int):
    """Leave a guild."""
    user_id = await token_check()
    await guild_check(user_id, guild_id)

    await remove_member(guild_id, user_id)

    return '', 204


# @bp.route('/@me/connections', methods=['GET'])
async def get_connections():
    pass


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


@bp.route('/<int:peer_id>/profile', methods=['GET'])
async def get_profile(peer_id: int):
    """Get a user's profile."""
    user_id = await token_check()

    # TODO: check if they have any mutual guilds,
    # and return empty profile if they don't.
    peer = await app.storage.get_user(peer_id)

    if not peer:
        return '', 404

    # actual premium status is determined by that
    # column being NULL or not
    peer_premium = await app.db.fetchval("""
    SELECT premium_since
    FROM users
    WHERE id = $1
    """, peer_id)

    # this is a rad sql query
    mutual_guilds = await app.db.fetch("""
    SELECT guild_id FROM members WHERE user_id = $1
    INTERSECT
    SELECT guild_id FROM members WHERE user_id = $2
    """, user_id, peer_id)

    mutual_guilds = [r['guild_id'] for r in mutual_guilds]
    mutual_res = []

    # ascending sorting
    for guild_id in sorted(mutual_guilds):

        nick = await app.db.fetchval("""
        SELECT nickname
        FROM members
        WHERE guild_id = $1 AND user_id = $2
        """, guild_id, peer_id)

        mutual_res.append({
            'id': str(guild_id),
            'nick': nick,
        })

    return jsonify({
        'user': peer,
        'connected_accounts': [],
        'premium_since': peer_premium,
        'mutual_guilds': mutual_res,
    })
