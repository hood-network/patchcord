"""

Litecord
Copyright (C) 2018-2019  Luna Mendes

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
# from litecord.schemas import validate
# from litecord.admin_schemas import GUILD_UPDATE

bp = Blueprint('guilds_admin', __name__)

@bp.route('/<int:guild_id>', methods=['GET'])
async def get_guild(guild_id: int):
    """Get a basic guild payload."""
    await admin_check()

    return jsonify(
        await app.storage.get_guild(guild_id)
    )

@bp.route('/<int:guild_id>', methods=['PATCH'])
async def update_guild(guild_id: int):
    await admin_check()

    # j = validate(await request.get_json(), GUILD_UPDATE)

    # TODO: add guild availability update, we don't store it, should we?
    # TODO: what happens to the other guild attributes when its
    # unavailable? do they vanish?

    guild = await app.storage.get_guild(guild_id)
    await app.dispatcher.dispatch_guild(guild_id, 'GUILD_UPDATE', guild)
    return jsonify(guild)
