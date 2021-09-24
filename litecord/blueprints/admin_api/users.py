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

from quart import Blueprint, jsonify, current_app as app, request

from litecord.auth import admin_check
from litecord.schemas import validate
from litecord.admin_schemas import USER_CREATE, USER_UPDATE
from litecord.errors import BadRequest, Forbidden
from litecord.utils import async_map
from litecord.enums import UserFlags
from litecord.common.users import (
    create_user,
    delete_user,
    user_disconnect,
    mass_user_update,
)

bp = Blueprint("users_admin", __name__)


@bp.route("", methods=["POST", "PUT"], strict_slashes=False)
async def _create_user():
    await admin_check()
    j = validate(await request.get_json(), USER_CREATE)
    user_id, _ = await create_user(j["username"], j["email"], j["password"])
    return jsonify(await app.storage.get_user(user_id))


def args_try(args: dict, typ, field: str, default):
    """Try to fetch a value from the request arguments,
    given a type."""
    try:
        return typ(args.get(field, default))
    except (TypeError, ValueError):
        raise BadRequest(f"invalid {field} value")


@bp.route("", methods=["GET"], strict_slashes=False)
async def _search_users():
    await admin_check()

    args = request.args

    username, discrim = args.get("username"), args.get("discriminator")

    per_page = args_try(args, int, "per_page", 20)
    page = args_try(args, int, "page", 0)

    if page < 0:
        raise BadRequest("invalid page number")

    if per_page > 50:
        raise BadRequest("invalid per page number")

    # any of those must be available.
    if not any((username, discrim)):
        raise BadRequest("must insert username or discrim")

    wheres, args = [], []

    if username:
        wheres.append("username LIKE '%' || $2 || '%'")
        args.append(username)

    if discrim:
        wheres.append(f"discriminator = ${len(args) + 2}")
        args.append(discrim)

    where_tot = "WHERE " if args else ""
    where_tot += " AND ".join(wheres)

    rows = await app.db.fetch(
        f"""
    SELECT id
    FROM users
    {where_tot}
    ORDER BY id ASC
    LIMIT {per_page}
    OFFSET ($1 * {per_page})
    """,
        page,
        *args,
    )

    rows = [r["id"] for r in rows]

    return jsonify(await async_map(app.storage.get_user, rows))


@bp.route("/<int:user_id>", methods=["DELETE"])
async def _delete_single_user(user_id: int):
    await admin_check()

    old_user = await app.storage.get_user(user_id)

    await delete_user(user_id)
    await user_disconnect(user_id)

    new_user = await app.storage.get_user(user_id)

    return jsonify({"old": old_user, "new": new_user})


@bp.route("/<int:user_id>", methods=["PATCH"])
async def patch_user(user_id: int):
    await admin_check()

    j = validate(await request.get_json(), USER_UPDATE)

    # get the original user for flags checking
    user = await app.storage.get_user(user_id)
    old_flags = UserFlags.from_int(user["flags"])

    # j.flags is already a UserFlags since we coerce it.
    if "flags" in j:
        new_flags = j["flags"]

        # disallow any changes to the staff badge
        if new_flags.is_staff != old_flags.is_staff:
            raise Forbidden("you can not change a users staff badge")

        await app.db.execute(
            """
        UPDATE users
        SET flags = $1
        WHERE id = $2
        """,
            new_flags.value,
            user_id,
        )

    public_user, _ = await mass_user_update(user_id)
    return jsonify(public_user)
