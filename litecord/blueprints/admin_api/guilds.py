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
from typing import List, TYPE_CHECKING

from litecord.auth import admin_check
from litecord.blueprints.guilds import handle_guild_create, handle_guild_update
from litecord.common.interop import guild_view
from litecord.schemas import validate
from litecord.admin_schemas import GUILD_UPDATE, FEATURES
from litecord.common.guilds import delete_guild
from litecord.errors import NotFound
from litecord.utils import extract_limit

if TYPE_CHECKING:
    from litecord.typing_hax import app, request
else:
    from quart import current_app as app, request

bp = Blueprint("guilds_admin", __name__)


async def _features_from_req() -> List[str]:
    j = validate(await request.get_json(), FEATURES)
    return [feature for feature in j["features"] or []]


async def _features(guild_id: int):
    return jsonify({"features": await app.storage.guild_features(guild_id) or []})


async def _update_features(guild_id: int, features: list):
    if "VANITY_URL" not in features:
        existing_inv = await app.storage.vanity_invite(guild_id)

        if existing_inv:
            await app.db.execute(
                """
            DELETE FROM vanity_invites
            WHERE guild_id = $1
            """,
                guild_id,
            )

            await app.db.execute(
                """
            DELETE FROM invites
            WHERE code = $1
            """,
                existing_inv,
            )

    await app.db.execute(
        """
    UPDATE guilds
    SET features = $1
    WHERE id = $2
    """,
        features,
        guild_id,
    )

    guild = await app.storage.get_guild_full(guild_id)
    await app.dispatcher.guild.dispatch(guild_id, ("GUILD_UPDATE", guild))


@bp.route("", methods=["GET"], strict_slashes=False)
async def query_guilds():
    await admin_check()

    limit = extract_limit(request, 1, 25, 100)
    j = validate(
        request.args.to_dict(),
        {
            "q": {"coerce": str, "required": False, "maxlength": 100},
            "offset": {"coerce": int, "default": 0},
        },
    )
    query = j.get("q") or ""
    offset = j["offset"]

    result = await app.storage.get_guilds(
        extra_clause=", COUNT(*) OVER() as total_results",
        where_clause="""
        WHERE name ILIKE '%'||$1||'%'
        ORDER BY name
        LIMIT $2 OFFSET $3
        """,
        args=(query, limit, offset),
        full=True,
    )

    total_results = result[0]["total_results"] if result else 0
    for guild in result:
        guild.pop("total_results")
    return jsonify({"guilds": result, "total_results": total_results})


@bp.route("", methods=["POST"], strict_slashes=False)
async def create_guild():
    """Create a new guild, assigning
    the user creating it as the owner and
    making them join."""
    user_id = await admin_check()
    j = validate(
        await request.get_json(),
        {
            **GUILD_UPDATE,
            "id": {"coerce": int, "required": False},
            "features": {"type": "list", "schema": {"coerce": str}, "required": False},
        },
    )
    guild_id = j.get("id") or app.winter_factory.snowflake()
    guild, extra = await handle_guild_create(
        user_id, guild_id, {"features": j.get("features")}
    )
    return jsonify({**guild, **extra}), 201


@bp.route("/<int:guild_id>", methods=["GET"])
async def get_guild(guild_id: int):
    """Get a basic guild payload."""
    await admin_check()

    guild = await app.storage.get_guild_full(guild_id)
    if not guild:
        raise NotFound(10004)

    return jsonify(guild_view(guild))


@bp.route("/<int:guild_id>", methods=["PATCH"])
async def update_guild(guild_id: int):
    await admin_check()

    j = validate(
        await request.get_json(),
        {**GUILD_UPDATE, "unavailable": {"coerce": bool, "required": False}},
    )

    if "features" in j and j["features"] is not None:
        features = await _features_from_req()
        await _update_features(guild_id, list(set(features)))

    old_unavailable = app.guild_store.get(guild_id, "unavailable")
    new_unavailable = j.get("unavailable", old_unavailable)
    app.guild_store.set(guild_id, "unavailable", new_unavailable)

    if old_unavailable and not new_unavailable:
        # Guild became available
        guild = await app.storage.get_guild_full(guild_id)
        await app.dispatcher.guild.dispatch(
            guild_id, ("GUILD_CREATE", {**guild, "unavailable": False})
        )
    elif not old_unavailable and new_unavailable:
        # Guild became unavailable
        await app.dispatcher.guild.dispatch(
            guild_id,
            (
                "GUILD_DELETE",
                {"id": guild_id, "guild_id": guild_id, "unavailable": True},
            ),
        )

    guild = await handle_guild_update(guild_id, False)
    return jsonify(guild)


@bp.route("/<int:guild_id>/delete", methods=["POST"])
@bp.route("/<int:guild_id>", methods=["DELETE"])
async def delete_guild_as_admin(guild_id):
    """Delete a single guild."""
    await admin_check()
    await delete_guild(guild_id)
    return "", 204


@bp.route("/<int:guild_id>/features", methods=["GET"])
async def get_features(guild_id: int):
    """Get the feature list of a guild"""
    await admin_check()
    return await _features(guild_id)


@bp.route("/<int:guild_id>/features", methods=["PUT"])
async def replace_features(guild_id: int):
    """Replace the feature list in a guild"""
    await admin_check()
    features = await _features_from_req()

    await _update_features(guild_id, list(set(features)))
    return await _features(guild_id)


@bp.route("/<int:guild_id>/features", methods=["PATCH"])
async def insert_features(guild_id: int):
    """Insert a feature on a guild."""
    await admin_check()
    to_add = await _features_from_req()
    features = set(await app.storage.guild_features(guild_id))

    # i'm assuming set.add is mostly safe
    for feature in to_add:
        features.add(feature)

    await _update_features(guild_id, list(features))
    return await _features(guild_id)


@bp.route("/<int:guild_id>/features", methods=["DELETE"])
async def remove_features(guild_id: int):
    """Remove a feature from a guild"""
    await admin_check()
    to_remove = await _features_from_req()
    features = set(await app.storage.guild_features(guild_id))

    for feature in to_remove:
        try:
            features.remove(feature)
        except KeyError:
            pass

    await _update_features(guild_id, list(features))
    return await _features(guild_id)
