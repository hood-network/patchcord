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

import string
from random import choice
from typing import Optional, TYPE_CHECKING

from quart import Blueprint, jsonify

from litecord.auth import admin_check
from ...errors import InternalServerError, NotFound
from litecord.types import timestamp_
from litecord.schemas import validate
from litecord.admin_schemas import INSTANCE_INVITE

if TYPE_CHECKING:
    from litecord.typing_hax import app, request
else:
    from quart import current_app as app, request

bp = Blueprint("instance_invites", __name__)
ALPHABET = string.ascii_lowercase + string.ascii_uppercase + string.digits


def _gen_inv() -> str:
    """Generate an invite code"""
    return "".join(choice(ALPHABET) for _ in range(6))


async def gen_inv(ctx) -> Optional[str]:
    """Generate an invite."""
    for _ in range(10):
        possible_inv = _gen_inv()

        created_at = await ctx.db.fetchval(
            """
        SELECT created_at
        FROM instance_invites
        WHERE code = $1
        """,
            possible_inv,
        )

        if created_at is None:
            return possible_inv

    return None


@bp.route("", methods=["GET"], strict_slashes=False)
async def _all_instance_invites():
    await admin_check()

    rows = await app.db.fetch(
        """
    SELECT code, created_at, uses, max_uses
    FROM instance_invites
    """
    )

    rows = [dict(row) for row in rows]

    for row in rows:
        row["created_at"] = timestamp_(row["created_at"])

    return jsonify(rows)


@bp.route("", methods=["POST"], strict_slashes=False)
async def _create_invite():
    await admin_check()

    j = validate(await request.get_json(), INSTANCE_INVITE)

    code = await gen_inv(app)
    if code is None:
        raise InternalServerError()

    await app.db.execute(
        """
    INSERT INTO instance_invites (code, max_uses)
    VALUES ($1, $2)
    """,
        code,
        j["max_uses"],
    )

    inv = await app.db.fetchrow(
        """
        SELECT code, created_at, uses, max_uses
        FROM instance_invites
        WHERE code = $1
        """,
        code,
    )
    dinv = dict(inv)
    dinv["created_at"] = timestamp_(dinv["created_at"])

    return jsonify(dinv)


@bp.route("/<invite>", methods=["GET"])
async def _get_invite(invite):
    inv = await app.db.fetchrow(
        """
        SELECT code, created_at, uses, max_uses
        FROM instance_invites
        WHERE code = $1
        """,
        invite,
    )

    if not inv:
        raise NotFound(10006)
    dinv = dict(inv)
    dinv["created_at"] = timestamp_(dinv["created_at"])
    return jsonify(dinv)


@bp.route("/<invite>", methods=["DELETE"])
async def _del_invite(invite: str):
    await admin_check()

    res = await app.db.execute(
        """
    DELETE FROM instance_invites
    WHERE code = $1
    """,
        invite,
    )
    if res == "DELETE 0":
        raise NotFound(10006)

    return "", 204
