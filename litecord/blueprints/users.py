import random

from asyncpg import UniqueViolationError
from quart import Blueprint, jsonify, request, current_app as app

from ..auth import token_check
from ..errors import Forbidden, BadRequest
from ..schemas import validate, USER_SETTINGS, \
    USER_UPDATE, GUILD_SETTINGS

from .guilds import guild_check
from .auth import hash_data, check_password, check_username_usage

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

    if 'avatar' in j:
        # TODO: update icon
        pass

    if 'new_password' in j and j['new_password']:
        await _check_pass(j, user)

        new_hash = await hash_data(j['new_password'])

        await app.db.execute("""
        UPDATE users
        SET password_hash = $1
        WHERE id = $2
        """, new_hash, user_id)

    user.pop('password_hash')
    await app.dispatcher.dispatch_user(
        user_id, 'USER_UPDATE', user)

    public_user = await app.storage.get_user(user_id)

    guild_ids = await app.storage.get_user_guilds(user_id)
    friend_ids = await app.storage.get_friend_ids(user_id)

    await app.dispatcher.dispatch_many(
        'guild', guild_ids, 'USER_UPDATE', public_user
    )

    await app.dispatcher.dispatch_many(
        'friend', friend_ids, 'USER_UPDATE', public_user
    )

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


@bp.route('/@me/notes/<int:target_id>', methods=['PUT'])
async def put_note(target_id: int):
    """Put a note to a user."""
    user_id = await token_check()

    j = await request.get_json()
    note = str(j['note'])

    # UPSERTs are beautiful
    await app.db.execute("""
    INSERT INTO notes (user_id, target_id, note)
    VALUES ($1, $2, $3)

    ON CONFLICT DO UPDATE SET
        note = $3
    WHERE
        user_id = $1 AND target_id = $2
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
    """Patch the users' current settings.

    More information on what settings exist
    is at Storage.get_user_settings and the schema.sql file.
    """
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


@bp.route('/@me/guilds/<int:guild_id>/settings', methods=['PATCH'])
async def patch_guild_settings(guild_id: int):
    """Update the users' guild settings for a given guild.

    Guild settings are usually related to notifications.
    """
    user_id = await token_check()
    await guild_check(user_id, guild_id)

    j = validate(await request.get_json(), GUILD_SETTINGS)

    # querying the guild settings information before modifying
    # will make sure they exist in the table.
    await app.storage.get_guild_settings_one(user_id, guild_id)

    for field in (k for k in j.keys() if k != 'channel_overrides'):
        await app.db.execute(f"""
        UPDATE guild_settings
        SET {field} = $1
        WHERE user_id = $2 AND guild_id = $3
        """, j[field], user_id, guild_id)

    chan_ids = await app.storage.get_channel_ids(guild_id)

    for chandata in j.get('channel_overrides', {}).items():
        chan_id, chan_overrides = chandata
        chan_id = int(chan_id)

        # ignore channels that aren't in the guild.
        if chan_id not in chan_ids:
            continue

        for field in chan_overrides:
            res = await app.db.execute(f"""
            UPDATE guild_settings_channel_overrides
            SET {field} = $1
            WHERE user_id = $2
            AND   guild_id = $3
            AND   channel_id = $4
            """, chan_overrides[field], user_id, guild_id, chan_id)

            if res == 'UPDATE 0':
                await app.db.execute(f"""
                INSERT INTO guild_settings_channel_overrides
                    (user_id, guild_id, channel_id, {field})
                VALUES ($1, $2, $3, $4)
                """, user_id, guild_id, chan_id, chan_overrides[field])

    settings = await app.storage.get_guild_settings_one(user_id, guild_id)

    await app.dispatcher.dispatch_user(
        user_id, 'USER_GUILD_SETTINGS_UPDATE', settings)

    return jsonify(settings)
