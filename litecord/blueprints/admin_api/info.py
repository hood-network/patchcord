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

from quart import Blueprint, jsonify
from typing import TYPE_CHECKING

from litecord.auth import admin_check

if TYPE_CHECKING:
    from litecord.typing_hax import app
else:
    from quart import current_app as app

bp = Blueprint("info_admin", __name__)


@bp.route("/db", methods=["GET"])
async def get_db_url():
    """Discover the app's DB URL."""
    await admin_check()

    db = app.config["POSTGRES"]
    host = db["host"]
    if host in ("localhost", "0.0.0.0"):
        host = app.config["MAIN_URL"]

    return jsonify(
        {
            "url": f"postgres://{db['user']}:{db['password']}@{host}:5432/{db['database']}"
        }
    )


@bp.route("/snowflake", methods=["GET"])
async def generate_snowflake():
    """Generate a snowflake."""
    await admin_check()
    return jsonify({"id": str(app.winter_factory.snowflake())})


@bp.route("/counts", methods=["GET"])
async def get_counts():
    """Get total counts of various things."""
    counts = await app.db.fetchrow(
        """
        SELECT COUNT(*) AS users,
            (SELECT COUNT(*) FROM icons) AS icons,
            (SELECT COUNT(*) FROM guilds) AS guilds,
            (SELECT COUNT(*) FROM bans) AS bans,
            (SELECT COUNT(*) FROM channels) AS channels,
            (SELECT COUNT(*) FROM guild_channels) AS guild_channels,
            (SELECT COUNT(*) FROM dm_channels) AS dms,
            (SELECT COUNT(*) FROM group_dm_channels) AS group_dms,
            (SELECT COUNT(*) FROM channel_overwrites) AS overwrites,
            (SELECT COUNT(*) FROM channel_pins) AS pins,
            (SELECT COUNT(*) FROM roles) AS roles,
            (SELECT COUNT(*) FROM messages) AS messages,
            (SELECT COUNT(*) FROM attachments) AS attachments,
            (SELECT COUNT(*) FROM message_reactions) AS reactions,
            (SELECT COUNT(*) FROM message_webhook_info) AS webhook_messages,
            (SELECT COUNT(*) FROM webhooks) AS webhooks,
            (SELECT COUNT(*) FROM invites) AS invites,
            (SELECT COUNT(*) FROM guild_emoji) AS emojis,
            (SELECT COUNT(*) FROM vanity_invites) AS vanities,
            (SELECT COUNT(*) FROM guild_integrations) AS integrations,
            (SELECT COUNT(*) FROM connections) AS connections,
            (SELECT COUNT(*) FROM relationships) AS relationships,
            (SELECT COUNT(*) FROM notes) AS notes
        FROM users
        """
    )

    counts = dict(counts)
    counts["private_channels"] = counts["dms"] + counts["group_dms"]
    return jsonify(counts)
