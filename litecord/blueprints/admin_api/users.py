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
from litecord.blueprints.auth import create_user
from litecord.schemas import validate
from litecord.admin_schemas import USER_CREATE

bp = Blueprint('users_admin', __name__)

@bp.route('', methods=['POST'])
async def _create_user():
    await admin_check()

    j = validate(await request.get_json(), USER_CREATE)

    user_id = await create_user(j['username'], j['email'], j['password'])

    return jsonify(
        await app.storage.get_user(user_id)
    )

