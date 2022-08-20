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
from typing import List

from litecord.auth import admin_check
from litecord.common.interop import guild_view
from litecord.schemas import validate
from litecord.admin_schemas import GUILD_UPDATE, FEATURES
from litecord.common.guilds import delete_guild
from litecord.errors import NotFound

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


@bp.route("/<int:guild_id>/features", methods=["PUT"])
async def replace_features(guild_id: int):
    """Replace the feature list in a guild"""
    await admin_check()
    features = await _features_from_req()

    await _update_features(guild_id, list(set(features)))
    return await _features(guild_id)


@bp.route("/<int:guild_id>/features", methods=["POST"])
async def insert_features(guild_id: int):
    """Insert a feature on a guild."""
    await admin_check()
    to_add = await _features_from_req()

    features = await app.storage.guild_features(guild_id)
    features = set(features)

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
    features = await app.storage.guild_features(guild_id)

    for feature in to_remove:
        try:
            features.remove(feature)
        except ValueError:
            pass

    await _update_features(guild_id, features)
    return await _features(guild_id)


@bp.route("/<int:guild_id>", methods=["GET"])
async def get_guild(guild_id: int):
    """Get a basic guild payload."""
    await admin_check()

    guild = await app.storage.get_guild(guild_id)

    if not guild:
        raise NotFound(10004)

    return jsonify(guild_view(guild))


@bp.route("/<int:guild_id>", methods=["PATCH"])
async def update_guild(guild_id: int):
    await admin_check()

    j = validate(await request.get_json(), GUILD_UPDATE)

    if "features" in j and j["featrures"] is not None:
        features = await _features_from_req()
        await _update_features(guild_id, list(set(features)))

    old_unavailable = app.guild_store.get(guild_id, "unavailable")
    new_unavailable = j.get("unavailable", old_unavailable)

    # always set unavailable status since new_unavailable will be
    # old_unavailable when not provided, so we don't need to check if
    # j.unavailable is there
    app.guild_store.set(guild_id, "unavailable", j["unavailable"])

    guild = await app.storage.get_guild(guild_id)

    # TODO: maybe we can just check guild['unavailable']...?

    if old_unavailable and not new_unavailable:
        # guild became available
        extra = await app.storage.get_guild_extra(guild_id)
        await app.dispatcher.guild.dispatch(guild_id, ("GUILD_CREATE", {**guild, **extra, "unavailable": False}))
    else:
        # guild became unavailable
        await app.dispatcher.guild.dispatch(guild_id, ("GUILD_DELETE", {**guild, "id": guild["id"]}))

    return jsonify(guild_view(guild))


@bp.route("/<int:guild_id>/delete", methods=["POST"])
@bp.route("/<int:guild_id>", methods=["DELETE"])
async def delete_guild_as_admin(guild_id):
    """Delete a single guild via the admin API without ownership checks."""
    await admin_check()
    await delete_guild(guild_id)
    return "", 204
