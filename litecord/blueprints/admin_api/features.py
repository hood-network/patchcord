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
from typing import List

from quart import Blueprint, current_app as app, jsonify, request

from litecord.auth import admin_check
from litecord.errors import BadRequest
from litecord.schemas import validate, FEATURES

bp = Blueprint('features_admin', __name__)


async def _features_from_req() -> List[str]:
    j = validate(await request.get_json(), FEATURES)
    return [feature.value for feature in j['features']]


async def _features(guild_id: int):
    return jsonify({
        'features': await app.storage.guild_features(guild_id)
    })


async def _update_features(guild_id: int, features: list):
    await app.db.execute("""
    UPDATE guilds
    SET features = $1
    WHERE id = $2
    """, features, guild_id)


@bp.route('/<int:guild_id>/features', methods=['PATCH'])
async def replace_features(guild_id: int):
    """Replace the feature list in a guild"""
    await admin_check()
    features = await _features_from_req()

    # yes, we need to pass it to a set and then to a list before
    # doing anything, since the api client might just
    # shove 200 repeated features to us.
    await _update_features(guild_id, list(set(features)))
    return await _features(guild_id)


@bp.route('/<int:guild_id>/features', methods=['PUT'])
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


@bp.route('/<int:guild_id>/<feature>', methods=['DELETE'])
async def remove_feature(guild_id: int):
    """Remove a feature from a guild"""
    await admin_check()
    to_remove = await _features_from_req()
    features = await app.storage.guild_features(guild_id)

    for feature in to_remove:
        try:
            features.remove(feature)
        except ValueError:
            raise BadRequest('Trying to remove already removed feature.')

    await _update_features(guild_id, features)
    return await _features(guild_id)
