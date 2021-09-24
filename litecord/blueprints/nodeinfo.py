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

from quart import Blueprint, current_app as app, jsonify, request

bp = Blueprint("nodeinfo", __name__)


@bp.route("/.well-known/nodeinfo")
async def _dummy_nodeinfo_index():
    proto = "http" if not app.config["IS_SSL"] else "https"
    main_url = app.config.get("MAIN_URL", request.host)

    return jsonify(
        {
            "links": [
                {
                    "href": f"{proto}://{main_url}/nodeinfo/2.0.json",
                    "rel": "http://nodeinfo.diaspora.software/ns/schema/2.0",
                },
                {
                    "href": f"{proto}://{main_url}/nodeinfo/2.1.json",
                    "rel": "http://nodeinfo.diaspora.software/ns/schema/2.1",
                },
            ]
        }
    )


async def fetch_nodeinfo_20():
    usercount = await app.db.fetchval(
        """
    SELECT COUNT(*)
    FROM users
    """
    )

    message_count = await app.db.fetchval(
        """
    SELECT COUNT(*)
    FROM messages
    """
    )

    return {
        "metadata": {
            "features": ["discord_api"],
            "nodeDescription": "A Litecord instance",
            "nodeName": "Litecord/Nya",
            "private": False,
            "federation": {},
        },
        "openRegistrations": app.config["REGISTRATIONS"],
        "protocols": [],
        "software": {"name": "litecord", "version": "litecord v0"},
        "services": {"inbound": [], "outbound": []},
        "usage": {"localPosts": message_count, "users": {"total": usercount}},
        "version": "2.0",
    }


@bp.route("/nodeinfo/2.0.json")
async def _nodeinfo_20():
    """Handler for nodeinfo 2.0."""
    raw_nodeinfo = await fetch_nodeinfo_20()
    return jsonify(raw_nodeinfo)


@bp.route("/nodeinfo/2.1.json")
async def _nodeinfo_21():
    """Handler for nodeinfo 2.1."""
    raw_nodeinfo = await fetch_nodeinfo_20()

    raw_nodeinfo["software"]["repository"] = "https://gitlab.com/litecord/litecord"
    raw_nodeinfo["version"] = "2.1"

    return jsonify(raw_nodeinfo)
