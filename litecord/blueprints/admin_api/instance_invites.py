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

from quart import Blueprint, jsonify, current_app as app

from litecord.auth import admin_check

bp = Blueprint('instance_invites', __name__)


@bp.route('', methods=['GET'])
async def _all_instance_invites():
    await admin_check()

    rows = await app.db.fetch("""
    SELECT code, created_at, uses, max_uses
    FROM instance_invites
    """)

    return jsonify([dict(row) for row in rows])
