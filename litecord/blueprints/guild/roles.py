from typing import List, Dict, Any, Union

from quart import Blueprint, request, current_app as app, jsonify

from litecord.auth import token_check

from litecord.blueprints.checks import (
    guild_check, guild_owner_check
)
from litecord.schemas import (
    validate, ROLE_CREATE, ROLE_UPDATE, ROLE_UPDATE_POSITION
)

from litecord.snowflake import get_snowflake
from litecord.utils import dict_get

DEFAULT_EVERYONE_PERMS = 104324161
bp = Blueprint('guild_roles', __name__)


@bp.route('/<int:guild_id>/roles', methods=['GET'])
async def get_guild_roles(guild_id):
    """Get all roles in a guild."""
    user_id = await token_check()
    await guild_check(user_id, guild_id)

    return jsonify(
        await app.storage.get_role_data(guild_id)
    )


async def _maybe_lg(guild_id: int, event: str,
                    role, force: bool = False):
    # sometimes we want to dispatch an event
    # even if the role isn't hoisted

    # an example of such a case is when a role loses
    # its hoist status.

    # check if is a dict first because role_delete
    # only receives the role id.
    if isinstance(role, dict) and not role['hoist'] and not force:
        return

    await app.dispatcher.dispatch(
        'lazy_guild', guild_id, event, role)


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

    # we need to update the lazy guild handlers for the newly created group
    await _maybe_lg(guild_id, 'new_role', role)

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

    await _maybe_lg(guild_id, 'role_pos_upd', role)

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


def gen_pairs(list_of_changes: List[Dict[str, int]],
              current_state: Dict[int, int],
              blacklist: List[int] = None) -> List[tuple]:
    """Generate a list of pairs that, when applied to the database,
    will generate the desired state given in list_of_changes.

    We must check if the given list_of_changes isn't overwriting an
    element's (such as a role or a channel) position to an existing one,
    without there having an already existing change for the other one.

    Here's a pratical explanation with roles:

    R1 (in position RP1) wants to be in the same position
    as R2 (currently in position RP2).

    So, if we did the simpler approach, list_of_changes
    would just contain the preferred change: (R1, RP2).

    With gen_pairs, there MUST be a (R2, RP1) in list_of_changes,
    if there is, the given result in gen_pairs will be a pair
    ((R1, RP2), (R2, RP1)) which is then used to actually
    update the roles' positions in a transaction.

    Parameters
    ----------
    list_of_changes:
        A list of dictionaries with ``id`` and ``position``
        fields, describing the preferred changes.
    current_state:
        Dictionary containing the current state of the list
        of elements (roles or channels). Points position
        to element ID.
    blacklist:
        List of IDs that shouldn't be moved.

    Returns
    -------
    list
        List of swaps to do to achieve the preferred
        state given by ``list_of_changes``.
    """
    pairs = []
    blacklist = blacklist or []

    preferred_state = {element['id']: element['position']
                       for element in list_of_changes}

    for blacklisted_id in blacklist:
        preferred_state.pop(blacklisted_id)

    # for each change, we must find a matching change
    # in the same list, so we can make a swap pair
    for change in list_of_changes:
        element_1, new_pos_1 = change['id'], change['position']

        # check current pairs
        # so we don't repeat an element
        flag = False

        for pair in pairs:
            if (element_1, new_pos_1) in pair:
                flag = True

        # skip if found
        if flag:
            continue

        # search if there is a role/channel in the
        # position we want to change to
        element_2 = current_state.get(new_pos_1)

        # if there is, is that existing channel being
        # swapped to another position?
        new_pos_2 = preferred_state.get(element_2)

        # if its being swapped to leave space, add it
        # to the pairs list
        if new_pos_2:
            pairs.append(
                ((element_1, new_pos_1), (element_2, new_pos_2))
            )

    return pairs


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

    all_roles = await app.storage.get_role_data(guild_id)

    # we'll have to calculate pairs of changing roles,
    # then do the changes, etc.
    roles_pos = {role['position']: int(role['id']) for role in all_roles}

    # TODO: check if the user can even change the roles in the first place,
    #       preferrably when we have a proper perms system.

    pairs = gen_pairs(
        j,
        roles_pos,

        # always ignore people trying to change
        # the @everyone's role position
        [guild_id]
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
    await _maybe_lg(guild_id, 'role_update', role, True)
    return jsonify(role)


@bp.route('/<int:guild_id>/roles/<int:role_id>', methods=['DELETE'])
async def delete_guild_role(guild_id, role_id):
    """Delete a role.

    Dispatches GUILD_ROLE_DELETE.
    """
    user_id = await token_check()

    # TODO: check MANAGE_ROLES
    await guild_owner_check(user_id, guild_id)

    res = await app.db.execute("""
    DELETE FROM roles
    WHERE guild_id = $1 AND id = $2
    """, guild_id, role_id)

    if res == 'DELETE 0':
        return '', 204

    await _maybe_lg(guild_id, 'role_delete', role_id, True)

    await app.dispatcher.dispatch_guild(guild_id, 'GUILD_ROLE_DELETE', {
        'guild_id': str(guild_id),
        'role_id': str(role_id),
    })

    return '', 204
