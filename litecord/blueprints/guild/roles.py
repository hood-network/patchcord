from quart import Blueprint, request, current_app as app, jsonify

from litecord.auth import token_check

# from litecord.blueprints.checks import guild_check
from litecord.blueprints.checks import guild_owner_check
from litecord.snowflake import get_snowflake
from litecord.utils import dict_get

from litecord.schemas import (
    validate, ROLE_CREATE, ROLE_UPDATE, ROLE_UPDATE_POSITION
)

DEFAULT_EVERYONE_PERMS = 104324161
bp = Blueprint('guild_roles', __name__)


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
