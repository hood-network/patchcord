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
from litecord.schemas import validate
from litecord.admin_schemas import VOICE_SERVER, VOICE_REGION

bp = Blueprint('voice_admin', __name__)


@bp.route('/regions/<region>', methods=['GET'])
async def get_region_servers(region):
    """Return a list of all servers for a region."""
    _user_id = await admin_check()
    servers = await app.voice.voice_server_list(region)
    return jsonify(servers)


@bp.route('/regions', methods=['PUT'])
async def insert_new_region():
    """Create a voice region."""
    _user_id = await admin_check()
    j = validate(await request.get_json(), VOICE_REGION)

    j['id'] = j['id'].lower()

    await app.db.execute("""
    INSERT INTO voice_regions (id, name, vip, deprecated, custom)
    VALUES ($1, $2, $3, $4, $5)
    """, j['id'], j['name'], j['vip'], j['deprecated'], j['custom'])

    return jsonify(
        await app.storage.all_voice_regions()
    )


@bp.route('/regions/<region>/servers', methods=['PUT'])
async def put_region_server(region):
    """Insert a voice server to a region"""
    _user_id = await admin_check()
    j = validate(await request.get_json(), VOICE_SERVER)

    await app.db.execute("""
    INSERT INTO voice_servers (hostname, region)
    VALUES ($1, $2)
    """, j['hostname'], region)

    return '', 204


@bp.route('/regions/<region>/deprecate', methods=['PUT'])
async def deprecate_region(region):
    """Deprecate a voice region."""
    _user_id = await admin_check()

    # TODO: write this
    await app.voice.disable_region(region)

    await app.db.execute("""
    UPDATE voice_regions
    SET deprecated = true
    WHERE id = $1
    """, region)

    return '', 204
