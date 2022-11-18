"""

Litecord
Copyright (C) 2018-2021  Luna Mendes and Litecord Contributors

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

from typing import List, Dict, Tuple, Optional, TYPE_CHECKING

from quart import Blueprint, jsonify
from logbook import Logger

from litecord.auth import token_check

from litecord.blueprints.checks import guild_check, guild_perm_check
from litecord.common.interop import role_view
from litecord.errors import BadRequest, NotFound
from litecord.schemas import validate, ROLE_CREATE, ROLE_UPDATE, ROLE_UPDATE_POSITION

from litecord.utils import maybe_lazy_guild_dispatch
from litecord.common.guilds import create_role

if TYPE_CHECKING:
    from litecord.typing_hax import app, request
else:
    from quart import current_app as app, request

log = Logger(__name__)
bp = Blueprint("guild_roles", __name__)


@bp.route("/<int:guild_id>/roles", methods=["GET"])
async def get_guild_roles(guild_id):
    """Get all roles in a guild."""
    user_id = await token_check()
    await guild_check(user_id, guild_id)

    return jsonify(list(map(role_view, await app.storage.get_role_data(guild_id))))


@bp.route("/<int:guild_id>/roles", methods=["POST"])
async def create_guild_role(guild_id: int):
    """Add a role to a guild"""
    user_id = await token_check()

    await guild_perm_check(user_id, guild_id, "manage_roles")

    # client can just send null
    j = validate(await request.get_json() or {}, ROLE_CREATE)

    role_name = j["name"]
    j.pop("name")

    role = await create_role(guild_id, role_name, **j)

    return jsonify(role)


async def _role_update_dispatch(role_id: int, guild_id: int):
    """Dispatch a GUILD_ROLE_UPDATE with updated information on a role."""
    role = await app.storage.get_role(role_id, guild_id)

    await maybe_lazy_guild_dispatch(guild_id, "role_position_update", role)

    await app.dispatcher.guild.dispatch(
        guild_id, ("GUILD_ROLE_UPDATE", {"guild_id": str(guild_id), "role": role})
    )

    return role_view(role)


async def _role_pairs_update(guild_id: int, pairs: list):
    """Update the roles' positions.

    Dispatches GUILD_ROLE_UPDATE for all roles being updated.
    """
    updated = []
    conn = await app.db.acquire()

    async with conn.transaction():
        for pair in pairs:
            _id, pos = pair

            # update happens in a transaction
            # so we don't fuck it up
            await conn.execute(
                """
            UPDATE roles
            SET position = $1
            WHERE roles.id = $2
            """,
                pos,
                _id,
            )
            updated.append(_id)

    await app.db.release(conn)

    for _id in updated:
        await _role_update_dispatch(_id, guild_id)


PairList = List[Tuple[int, int]]


def gen_pairs(
    list_of_changes: List[Dict[str, int]],
    current_state: Dict[int, int],
    blacklist: Optional[List[int]] = None,
) -> PairList:
    """Generate a list of pairs that, when applied to the database,
    will generate the desired state given in list_of_changes.

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
        List of changes to do to achieve the preferred
        state given by ``list_of_changes``.
    """
    pairs: PairList = []
    blacklist = blacklist or []

    preferred_state = []
    for chan in current_state:
        preferred_state.insert(chan, current_state[chan])

    for blacklisted_id in blacklist:
        if blacklisted_id in preferred_state:
            preferred_state.remove(blacklisted_id)

    current_state = preferred_state.copy()

    # for each change, we must find a matching change
    # in the same list, so we can make a swap pair
    for change in list_of_changes:
        _id, pos = change["id"], change["position"]
        if _id not in preferred_state:
            continue

        preferred_state.remove(_id)
        preferred_state.insert(pos, _id)

    assert len(current_state) == len(preferred_state)

    for i in range(len(current_state)):
        if current_state[i] != preferred_state[i]:
            pairs.append((preferred_state[i], i))

    return pairs


@bp.route("/<int:guild_id>/roles", methods=["PATCH"])
async def update_guild_role_positions(guild_id):
    """Update the positions for a bunch of roles."""
    user_id = await token_check()

    await guild_perm_check(user_id, guild_id, "manage_roles")

    raw_j = await request.get_json()

    # we need to do this hackiness because thats
    # cerberus for ya.
    j = validate({"roles": raw_j}, ROLE_UPDATE_POSITION)

    # extract the list out
    roles = j["roles"]

    log.debug("role stuff: {!r}", roles)

    all_roles = await app.storage.get_role_data(guild_id)

    # we'll have to calculate pairs of changing roles,
    # then do the changes, etc.
    roles_pos = {role["position"]: int(role["id"]) for role in all_roles}

    # TODO: check if the user can even change the roles in the first place,
    #       preferrably when we have a proper perms system.

    # NOTE: ^ this is related to the positioning of the roles.

    pairs = gen_pairs(
        roles,
        roles_pos,
        # always ignore people trying to change
        # the @everyone's role position
        [guild_id],
    )

    await _role_pairs_update(guild_id, pairs)

    # return the list of all roles back
    return jsonify(list(map(role_view, await app.storage.get_role_data(guild_id))))


@bp.route("/<int:guild_id>/roles/<int:role_id>", methods=["PATCH"])
async def update_guild_role(guild_id, role_id):
    """Update a single role's information."""
    user_id = await token_check()

    await guild_perm_check(user_id, guild_id, "manage_roles")

    j = validate(await request.get_json(), ROLE_UPDATE)

    val = await app.db.fetchval(
        """
    SELECT id
    FROM roles
    WHERE guild_id = $1 AND id = $2
    """,
        guild_id,
        role_id,
    )
    if not val:
        raise NotFound(10011)

    # we only update ints on the db, not Permissions
    j["permissions"] = int(j["permissions"])

    if role_id == guild_id:
        j = {"permissions": j["permissions"]} if "permissions" in j else {}

    for field in j:
        await app.db.execute(
            f"""
        UPDATE roles
        SET {field} = $1
        WHERE roles.id = $2 AND roles.guild_id = $3
        """,
            j[field],
            role_id,
            guild_id,
        )

    role = await _role_update_dispatch(role_id, guild_id)
    await maybe_lazy_guild_dispatch(guild_id, "role_update", role, True)
    return jsonify(role)


@bp.route("/<int:guild_id>/roles/<int:role_id>", methods=["DELETE"])
async def delete_guild_role(guild_id, role_id):
    """Delete a role.

    Dispatches GUILD_ROLE_DELETE.
    """
    user_id = await token_check()

    await guild_perm_check(user_id, guild_id, "manage_roles")

    if role_id == guild_id:
        raise BadRequest(50028)

    res = await app.db.execute(
        """
    DELETE FROM roles
    WHERE guild_id = $1 AND id = $2
    """,
        guild_id,
        role_id,
    )

    if res == "DELETE 0":
        raise NotFound(10011)

    await maybe_lazy_guild_dispatch(guild_id, "role_delete", role_id, True)

    await app.dispatcher.guild.dispatch(
        guild_id,
        (
            "GUILD_ROLE_DELETE",
            {"guild_id": str(guild_id), "role_id": str(role_id)},
        ),
    )

    return "", 204


@bp.route("/<int:guild_id>/roles/member-counts", methods=["GET"])
async def role_member_counts(guild_id):
    """Get the member counts of all guild roles."""
    user_id = await token_check()

    await guild_check(user_id, guild_id)

    roles = await app.db.fetch(
        """
    SELECT id
    FROM roles
    WHERE guild_id = $1
    """,
        guild_id,
    )

    counts = {str(guild_id): 0}
    for role in roles:
        if role["id"] == guild_id:
            continue

        counts[str(role["id"])] = await app.db.fetchval(
            """
        SELECT COUNT(*)
        FROM member_roles
        WHERE role_id = $1
        """,
            role["id"],
        )

    return jsonify(counts)


@bp.route("/<int:guild_id>/roles/<int:role_id>/member-ids", methods=["GET"])
async def role_member_ids(guild_id, role_id):
    """Get a list of member IDs that have a given role."""
    user_id = await token_check()

    await guild_check(user_id, guild_id)

    # maximum is 100 but i dont wanna do that
    res = await app.db.fetch(
        """
    SELECT user_id
    FROM member_roles
    WHERE guild_id = $1 AND role_id = $2
    """,
        guild_id,
        role_id,
    )
    if not res:
        val = await app.db.fetchval(
            """
        SELECT id
        FROM roles
        WHERE guild_id = $1 AND id = $2
        """,
            guild_id,
            role_id,
        )
        if not val:
            raise NotFound(10011)
        res = []

    return jsonify([str(r["user_id"]) for r in res])


@bp.route("/<int:guild_id>/roles/<int:role_id>/members", methods=["PATCH"])
async def add_members_to_role(guild_id, role_id):
    """Add members to a role."""
    user_id = await token_check()

    await guild_perm_check(user_id, guild_id, "manage_roles")

    j = validate(
        await request.get_json(),
        {
            "member_ids": {
                "type": "list",
                "schema": {"coerce": int},
                "maxlength": 30,
                "required": True,
            }
        },
    )

    val = await app.db.fetchval(
        """
    SELECT id
    FROM roles
    WHERE guild_id = $1 AND id = $2
    """,
        guild_id,
        role_id,
    )
    if not val:
        raise NotFound(10011)

    members = []
    for id in j["member_ids"]:
        member = await app.storage.get_member(guild_id, id)
        if not member:
            continue

        if str(role_id) not in member["roles"]:
            await app.db.execute(
                """
            INSERT INTO member_roles (guild_id, user_id, role_id)
            VALUES ($1, $2, $3)
            """,
                guild_id,
                id,
                role_id,
            )

            member["roles"].append(str(role_id))

            # call pres_update for role changes.
            partial = {"roles": member["roles"]}

            await app.lazy_guild.pres_update(guild_id, id, partial)
            await app.dispatcher.guild.dispatch(
                guild_id,
                ("GUILD_MEMBER_UPDATE", {**{"guild_id": str(guild_id)}, **member}),
            )

        members.append(member)

    return jsonify({m["user_id"]: m for m in members})
