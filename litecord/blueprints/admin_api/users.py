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

from quart import Blueprint, jsonify
from typing import TYPE_CHECKING

from litecord.auth import admin_check
from litecord.schemas import validate, USER_UPDATE
from litecord.admin_schemas import USER_CREATE
from litecord.errors import BadRequest, NotFound
from litecord.utils import extract_limit
from litecord.blueprints.users import handle_user_update
from litecord.common.users import (
    create_user,
    delete_user,
    user_disconnect,
)

if TYPE_CHECKING:
    from litecord.typing_hax import app, request
else:
    from quart import current_app as app, request

bp = Blueprint("users_admin", __name__)


@bp.route("", methods=["POST"], strict_slashes=False)
async def _create_user():
    await admin_check()
    j = validate(await request.get_json(), USER_CREATE)
    user_id, _ = await create_user(
        j["username"], j["email"], j["password"], j.get("date_of_birth"), id=j.get("id")
    )
    return jsonify(await app.storage.get_user(user_id, True)), 201


def args_try(args: dict, typ, field: str, default):
    """Try to fetch a value from the request arguments,
    given a type."""
    try:
        return typ(args.get(field, default))
    except (TypeError, ValueError):
        raise BadRequest(message=f"invalid {field} value")


@bp.route("", methods=["GET"], strict_slashes=False)
async def query_users():
    await admin_check()

    limit = extract_limit(request, 1, 25, 100)
    j = validate(
        request.args.to_dict(),
        {
            "q": {"coerce": str, "required": False, "maxlength": 32},
            "offset": {"coerce": int, "default": 0},
        },
    )
    query = j.get("q") or ""
    offset = j["offset"]
    extra = ""
    args = (query, limit, offset)

    discriminator = None
    if "#" in query:
        query, _, discriminator = query.rpartition("#")
        try:
            discriminator = "%04d" % int(discriminator)
        except ValueError:
            discriminator = None

    if discriminator:
        extra = "AND discriminator = $4"
        args = (query, limit, offset, discriminator)

    result = await app.storage.get_users(
        secure=True,
        extra_clause=", COUNT(*) OVER() as total_results",
        where_clause=f"""
        WHERE username ILIKE '%'||$1||'%' {extra}
        ORDER BY username
        LIMIT $2 OFFSET $3
        """,
        args=args,
    )

    total_results = result[0]["total_results"] if result else 0
    for user in result:
        user.pop("total_results")
    return jsonify({"users": result, "total_results": total_results})


@bp.route("/@me", methods=["GET"])
async def get_me():
    user_id = await admin_check()
    return jsonify(await app.storage.get_user(user_id, True))


@bp.route("/<int:target_id>", methods=["GET"])
async def get_other(target_id):
    await admin_check()
    other = await app.storage.get_user(target_id, True)
    if not other:
        raise NotFound(10013)
    return jsonify(other)


@bp.route("/<int:user_id>", methods=["DELETE"])
@bp.route("/<int:user_id>/delete", methods=["POST"])
async def _delete_user(user_id: int):
    await admin_check()

    await delete_user(user_id)
    await user_disconnect(user_id)

    new_user = await app.storage.get_user(user_id, True)
    return jsonify(new_user)


@bp.route("/<int:user_id>", methods=["PATCH"])
async def patch_user(user_id: int):
    await admin_check()

    j = validate(await request.get_json(), USER_UPDATE)

    if "flags" in j and j["flags"] is not None:
        await app.db.execute(
            """
        UPDATE users
        SET flags = $1
        WHERE id = $2
        """,
            j["flags"],
            user_id,
        )
        j.pop("flags")

    private_user = await handle_user_update(user_id, False)
    return jsonify(private_user)


@bp.route("/<int:user_id>/channels", methods=["GET"])
async def user_dms(user_id: int):
    await admin_check()
    return jsonify(await app.user_storage.get_dms(user_id))


@bp.route("/<int:user_id>/relationships", methods=["GET"])
async def user_relationships(user_id: int):
    await admin_check()
    return jsonify(await app.user_storage.get_relationships(user_id))
