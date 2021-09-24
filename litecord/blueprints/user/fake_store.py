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

"""
fake routes for discord store
"""
from quart import Blueprint, jsonify

bp = Blueprint("fake_store", __name__)


@bp.route("/promotions")
async def _get_promotions():
    return jsonify([])


@bp.route("/users/@me/library")
async def _get_library():
    return jsonify([])


@bp.route("/users/@me/feed/settings")
async def _get_feed_settings():
    return jsonify(
        {
            "subscribed_games": [],
            "subscribed_users": [],
            "unsubscribed_users": [],
            "unsubscribed_games": [],
        }
    )
