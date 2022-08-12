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

from litecord.auth import token_check
from litecord.blueprints.checks import guild_perm_check
from litecord.errors import BadRequest

bp = Blueprint("science", __name__)


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


@bp.route("/partners/<int:guild_id>/requirements", methods=["GET"])
async def get_partner_requirements(guild_id: int):
    """Get the requirements for a guild to be a partner."""
    user_id = await token_check()
    await guild_perm_check(user_id, guild_id, "manage_guild")

    rules_channel = await app.db.fetchval(
        """
    SELECT rules_channel_id
    FROM guilds
    WHERE id = $1
    """,
        guild_id,
    )

    member_count = await app.db.fetchval(
        """
    SELECT COUNT(*)
    FROM members
    WHERE guild_id = $1
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
        "protected": False,
        "sufficient": True,
        "sufficient_without_grace_period": True,
        "valid_rules_channel": bool(rules_channel),
        "retention_healthy": True,
        "engagement_healthy": True,
        "age": True,
        "minimum_age": 0,
        "health_score": {"avg_nonnew_participators": member_count, "avg_nonnew_communicators": member_count, "num_intentful_joiners": member_count, "perc_ret_w1_intentful": member_count},
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
