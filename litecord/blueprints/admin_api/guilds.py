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
from litecord.admin_schemas import GUILD_UPDATE
from litecord.common.guilds import delete_guild
from litecord.errors import GuildNotFound

bp = Blueprint("guilds_admin", __name__)


@bp.route("/<int:guild_id>", methods=["GET"])
async def get_guild(guild_id: int):
    """Get a basic guild payload."""
    await admin_check()

    guild = await app.storage.get_guild(guild_id)

    if not guild:
        raise GuildNotFound()

    return jsonify(guild)


@bp.route("/<int:guild_id>", methods=["PATCH"])
async def update_guild(guild_id: int):
    await admin_check()

    j = validate(await request.get_json(), GUILD_UPDATE)

    # TODO: what happens to the other guild attributes when its
    # unavailable? do they vanish?
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
        await app.dispatcher.guild.dispatch(guild_id, ("GUILD_CREATE", guild))
    else:
        # guild became unavailable
        await app.dispatcher.guild.dispatch(guild_id, ("GUILD_DELETE", guild))

    return jsonify(guild)


@bp.route("/<int:guild_id>", methods=["DELETE"])
async def delete_guild_as_admin(guild_id):
    """Delete a single guild via the admin API without ownership checks."""
    await admin_check()
    await delete_guild(guild_id)
    return "", 204
