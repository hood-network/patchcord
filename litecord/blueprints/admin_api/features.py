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

from quart import Blueprint, current_app as app

from litecord.auth import admin_check
from litecord.errors import BadRequest

bp = Blueprint('features_admin', __name__)

FEATURES = [
    ''
]

@bp.route('/<int:guild_id>/<feature>', methods=['PUT'])
async def insert_feature(guild_id: int, feature: str):
    """Insert a feature on a guild."""
    await admin_check()

    # TODO
    if feature not in FEATURES:
        raise BadRequest('invalid feature')

    return '', 204


@bp.route('/<int:guild_id>/<feature>', methods=['DELETE'])
async def remove_feature(guild_id: int, feature: str):
    """Remove a feature from a guild"""
    await admin_check()
    # TODO
    await app.db
    return '', 204
