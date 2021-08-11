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

import time

from quart import Blueprint, jsonify, current_app as app

from ..auth import token_check

bp = Blueprint("gateway", __name__)


def get_gw():
    """Get the gateway's web"""
    proto = "wss://" if app.config["IS_SSL"] else "ws://"
    return f'{proto}{app.config["WEBSOCKET_URL"]}'


@bp.route("/gateway")
def api_gateway():
    """Get the raw URL."""
    return jsonify({"url": get_gw()})


@bp.route("/gateway/bot")
async def api_gateway_bot():
    user_id = await token_check()

    guild_count = await app.db.fetchval(
        """
    SELECT COUNT(*)
    FROM members
    WHERE user_id = $1
    """,
        user_id,
    )

    shards = max(int(guild_count / 1000), 1)

    # get _ws.session ratelimit
    ratelimit = app.ratelimiter.get_ratelimit("_ws.session")
    bucket = ratelimit.get_bucket(user_id)

    # timestamp of bucket reset
    reset_ts = bucket._window + bucket.second

    # how many seconds until bucket reset
    # TODO: this logic should be changed to follow update_rate_limit's
    # except we can't just call it since we don't use it here, but
    # on the gateway side.
    reset_after_ts = reset_ts - time.time()

    # reset_after_ts must not be negative
    if reset_after_ts < 0:
        reset_after_ts = 0

    return jsonify(
        {
            "url": get_gw(),
            "shards": shards,
            "session_start_limit": {
                "total": bucket.requests,
                "remaining": bucket._tokens,
                "reset_after": int(reset_after_ts * 1000),
                "max_concurrency": 1,
            },
        }
    )
