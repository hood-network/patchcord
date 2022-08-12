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

from quart import Blueprint, jsonify, request, current_app as app
import json

from litecord.auth import token_check
from litecord.blueprints.checks import guild_perm_check
from litecord.errors import BadRequest

bp = Blueprint("science", __name__)

try:
    with open("assets/discovery_categories.json", "r") as f:
        DISCOVERY_CATEGORIES = json.load(f)
except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
    DISCOVERY_CATEGORIES = {}


@bp.route("/science", methods=["POST"])
async def science():
    return "", 204


@bp.route("/applications", methods=["GET"])
@bp.route("/teams", methods=["GET"])
@bp.route("/outbound-promotions", methods=["GET"])
async def applications():
    return jsonify([])


@bp.route("/experiments", methods=["GET"])
async def experiments():
    return jsonify({"assignments": []})


@bp.route("/discovery/categories", methods=["GET"])
async def get_discovery_categories():
    """Get discovery categories"""
    primary_only = request.args.get("primary_only", False, type=bool)
    if primary_only:
        return jsonify(cat for cat in DISCOVERY_CATEGORIES if cat["is_primary"])
    return jsonify(DISCOVERY_CATEGORIES)


@bp.route("/partners/<int:guild_id>/requirements", methods=["GET"])
async def get_partner_requirements(guild_id: int):
    """Get the requirements for a guild to be a partner."""
    user_id = await token_check()
    await guild_perm_check(user_id, guild_id, "manage_guild")

    data = await app.db.fetch(
        """
    SELECT rules_channel_id, mfa_level
    FROM guilds
    WHERE id = $1
    """,
        guild_id,
    )

    # Currently we just always say that a guild is partnerable
    data = {
        "guild_id": str(guild_id),
        "safe_enviroment": True,
        "healthy": True,
        "health_score_pending": False,
        "size": True,
        "nsfw_properties": {},
        "protected": bool(data["mfa_level"]),
        "sufficient": True,
        "sufficient_without_grace_period": True,
        "valid_rules_channel": bool(data["rules_channel_id"]),
        "retention_healthy": True,
        "engagement_healthy": True,
        "age": True,
        "minimum_age": 7,
        "health_score": {"avg_nonnew_participators": None, "avg_nonnew_communicators": None, "num_intentful_joiners": None, "perc_ret_w1_intentful": None},
        "minimum_size": 1,
    }
    return jsonify(data)


@bp.route("/partners/apply", methods=["POST"])
async def partners_apply():
    user_id = await token_check()

    try:
        guild_id = int((await request.get_json())["guild_id"])
    except (KeyError, ValueError):
        raise BadRequest("guild_id is required")

    await guild_perm_check(user_id, guild_id, "manage_guild")

    features = await app.storage.get_guild_features(guild_id) or []
    if "PARTNERED" in features:
        return "", 204

    features.append("PARTNERED")
    features.append("VANITY_URL")
    features.append("INVITE_SPLASH")
    features.append("BANNER")

    await app.db.execute(
        """
    UPDATE guilds
    SET features = $1
    WHERE id = $2
    """,
        features,
        guild_id,
    )

    guild = await app.storage.get_guild_full(guild_id, user_id, api_version=request.discord_api_version)
    await app.dispatcher.guild.dispatch(guild_id, ("GUILD_UPDATE", guild))

    return "", 204
