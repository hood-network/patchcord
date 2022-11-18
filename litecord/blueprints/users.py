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

from typing import List, TYPE_CHECKING

import asyncio
from asyncpg import UniqueViolationError
from datetime import datetime
from quart import Blueprint, jsonify
from logbook import Logger

from litecord.types import timestamp_

from ..errors import BadRequest, ManualFormError, MissingAccess, NotFound
from ..schemas import validate, USER_UPDATE, GET_MENTIONS
from ..utils import extract_limit, str_bool

from .guilds import guild_check
from litecord.auth import is_staff, token_check, hash_data
from litecord.common.guilds import remove_member

from litecord.enums import PremiumType, UserFlags
from litecord.images import parse_data_uri
from litecord.permissions import base_permissions

from litecord.blueprints.auth import check_password
from litecord.utils import to_update, toggle_flag
from litecord.common.messages import PLAN_ID_TO_TYPE
from litecord.common.interop import message_view
from litecord.common.users import (
    mass_user_update,
    delete_user,
    check_username_usage,
    roll_discrim,
    user_disconnect,
)

if TYPE_CHECKING:
    from litecord.typing_hax import app, request
else:
    from quart import current_app as app, request

bp = Blueprint("user", __name__)
log = Logger(__name__)


@bp.route("", methods=["GET"], strict_slashes=False)
async def query_users():
    """Query available users."""
    user_id = await token_check()

    limit = extract_limit(request, 1, 25, 100)
    j = validate(
        request.args.to_dict(),
        {"q": {"coerce": str, "required": True, "minlength": 2, "maxlength": 32}},
    )
    query = j["q"]

    result = await app.storage.get_users(
        where_clause="""
        WHERE username ILIKE '%'||$1||'%'
        AND CARDINALITY(ARRAY((SELECT guild_id FROM members WHERE user_id = id INTERSECT SELECT guild_id FROM members WHERE user_id = $2))) > 0
        ORDER BY username
        LIMIT $3
        """,
        args=(query, user_id, limit),
    )

    return jsonify(result)


@bp.route("/@me", methods=["GET"])
async def get_me():
    """Get the current user's information."""
    user_id = await token_check()
    user = await app.storage.get_user(user_id, True)
    return jsonify(user)


@bp.route("/<int:target_id>", methods=["GET"])
async def get_other(target_id):
    """Get any user, given the user ID."""
    await token_check()
    other = await app.storage.get_user(target_id)
    if not other:
        raise NotFound(10013)
    return jsonify(other)


async def _try_username_patch(user_id, new_username: str) -> str:
    await check_username_usage(new_username)
    discrim = None

    try:
        await app.db.execute(
            """
        UPDATE users
        SET username = $1
        WHERE users.id = $2
        """,
            new_username,
            user_id,
        )

        return await app.db.fetchval(
            """
        SELECT discriminator
        FROM users
        WHERE users.id = $1
        """,
            user_id,
        )
    except UniqueViolationError:
        discrim = await roll_discrim(new_username)

        if not discrim:
            raise BadRequest(30006)

        await app.db.execute(
            """
        UPDATE users
        SET username = $1, discriminator = $2
        WHERE users.id = $3
        """,
            new_username,
            discrim,
            user_id,
        )

    return discrim


async def _try_discrim_patch(user_id, new_discrim: str):
    try:
        await app.db.execute(
            """
        UPDATE users
        SET discriminator = $1
        WHERE id = $2
        """,
            new_discrim,
            user_id,
        )
    except UniqueViolationError:
        raise BadRequest(30006)


async def _check_pass(j, user):
    # Do not do password checks on unclaimed accounts
    if user["email"] is None:
        return

    if not j["password"]:
        raise ManualFormError(
            password={
                "code": "PASSWORD_DOES_NOT_MATCH",
                "message": "Password does not match.",
            }
        )

    phash = user["password_hash"]
    if not await check_password(phash, j["password"]):
        raise ManualFormError(
            password={
                "code": "PASSWORD_DOES_NOT_MATCH",
                "message": "Password does not match.",
            }
        )


@bp.route("/@me", methods=["PATCH"])
@bp.route("/@me/profile", methods=["PATCH"])
async def patch_me():
    """Patch the current user's information."""
    user_id = await token_check()
    return jsonify(await handle_user_update(user_id))


async def handle_user_update(user_id: int, check_password: bool = True):
    j = validate(await request.get_json(), USER_UPDATE)
    user = await app.storage.get_user(user_id, True)

    user["password_hash"] = await app.db.fetchval(
        """
    SELECT password_hash
    FROM users
    WHERE id = $1
    """,
        user_id,
    )

    if to_update(j, user, "username"):
        if check_password:
            await _check_pass(j, user)

        discrim = await _try_username_patch(user_id, j["username"])
        user["username"] = j["username"]
        user["discriminator"] = discrim

    if to_update(j, user, "discriminator"):
        if check_password:
            await _check_pass(j, user)

        try:
            new_discrim = "%04d" % int(j["discriminator"])
        except (ValueError, TypeError):
            pass
        else:
            if new_discrim != user["discriminator"]:
                await _try_discrim_patch(user_id, new_discrim)
                user["discriminator"] = new_discrim

    if to_update(j, user, "email"):
        if check_password:
            await _check_pass(j, user)

        await app.db.execute(
            """
        UPDATE users
        SET email = $1, verified = false
        WHERE id = $2
        """,
            j["email"],
            user_id,
        )
        user["email"] = j["email"]
        user["verified"] = False

    # only update if values are different
    # from what the user gave.

    # this will return false if the client
    # sends j['avatar'] as the user's
    # original avatar hash, as they're the
    # same.

    # IconManager.update will take care of validating
    # the value once put()-ing
    if to_update(j, user, "avatar"):
        mime, _ = parse_data_uri(j["avatar"])

        no_gif = False
        if mime == "image/gif" and user["premium_type"] == PremiumType.NONE:
            no_gif = True

        new_icon = await app.icons.update(
            "user_avatar", user_id, j["avatar"], size=(1024, 1024), always_icon=True
        )

        await app.db.execute(
            """
        UPDATE users
        SET avatar = $1
        WHERE id = $2
        """,
            new_icon.icon_hash.lstrip("a_")
            if (no_gif and new_icon.icon_hash)
            else new_icon.icon_hash,
            user_id,
        )

    if to_update(j, user, "avatar_decoration"):
        if not j["avatar_decoration"] or user["premium_type"] == PremiumType.TIER_2:
            new_icon = await app.icons.update(
                "user_avatar_decoration",
                user_id,
                j["avatar_decoration"],
                always_icon=True,
            )

            await app.db.execute(
                """
            UPDATE users
            SET avatar_decoration = $1
            WHERE id = $2
            """,
                new_icon.icon_hash,
                user_id,
            )

    if to_update(j, user, "banner"):
        if not j["banner"] or user["premium_type"] == PremiumType.TIER_2:
            new_icon = await app.icons.update(
                "user_banner", user_id, j["banner"], always_icon=True
            )

            await app.db.execute(
                """
            UPDATE users
            SET banner = $1
            WHERE id = $2
            """,
                new_icon.icon_hash,
                user_id,
            )

    if to_update(j, user, "bio"):
        await app.db.execute(
            """
            UPDATE users
            SET bio = $1
            WHERE id = $2
            """,
            j["bio"] or "",
            user_id,
        )

    if to_update(j, user, "pronouns"):
        await app.db.execute(
            """
            UPDATE users
            SET pronouns = $1
            WHERE id = $2
            """,
            j["pronouns"] or "",
            user_id,
        )

    if "banner_color" in j and "accent_color" not in j:
        if not j["banner_color"]:
            j["accent_color"] = None
        else:
            try:
                j["accent_color"] = int(j["banner_color"].lstrip("#"), base=16)
            except ValueError:
                pass

    if to_update(j, user, "accent_color"):
        await app.db.execute(
            """
            UPDATE users
            SET accent_color = $1
            WHERE id = $2
            """,
            j["accent_color"] or None,
            user_id,
        )

    if to_update(j, user, "theme_colors"):
        if not j["theme_colors"] or user["premium_type"] == PremiumType.TIER_2:
            await app.db.execute(
                """
                UPDATE users
                SET theme_colors = $1
                WHERE id = $2
                """,
                j["theme_colors"] or None,
                user_id,
            )

    # TODO: Unclaimed accounts

    if "new_password" in j and j["new_password"]:
        if check_password:
            await _check_pass(j, user)

        new_hash = await hash_data(j["new_password"])
        await app.db.execute(
            """
        UPDATE users
        SET password_hash = $1
        WHERE id = $2
        """,
            new_hash,
            user_id,
        )

    if j.get("flags"):
        old_flags = UserFlags.from_int(user["flags"])
        new_flags = UserFlags.from_int(j["flags"])

        toggle_flag(
            old_flags, UserFlags.premium_dismissed, new_flags.is_premium_dismissed
        )
        toggle_flag(
            old_flags, UserFlags.unread_urgent_system, new_flags.is_unread_urgent_system
        )
        toggle_flag(old_flags, UserFlags.disable_premium, new_flags.is_disable_premium)

        if old_flags.value != user["flags"]:
            await app.db.execute(
                """
            UPDATE users
            SET flags = $1
            WHERE id = $2
            """,
                old_flags.value,
                user_id,
            )

    if "date_of_birth" in j:
        date_of_birth = await app.db.fetchval(
            """
        SELECT date_of_birth
        FROM users
        WHERE id = $1
        """,
            user_id,
        )

        if date_of_birth:
            raise ManualFormError(
                date_of_birth={
                    "code": "DATE_OF_BIRTH_IMMUTABLE",
                    "message": "You cannot update your date of birth.",
                }
            )

        await app.db.execute(
            """
        UPDATE users
        SET date_of_birth = $1
        WHERE id = $2
        """,
            datetime.strptime(j["date_of_birth"], "%Y-%m-%d"),
            user_id,
        )

    user.pop("password_hash")

    _, private_user = await mass_user_update(user_id)
    return private_user


@bp.route("/@me/guilds", methods=["GET"])
async def get_me_guilds():
    """Get partial user guilds."""
    user_id = await token_check()
    guild_ids = await app.user_storage.get_user_guilds(user_id)

    partials = []

    with_counts = request.args.get("with_counts", type=str_bool)

    for guild_id in guild_ids:
        partial = await app.db.fetchrow(
            """
        SELECT id::text, name, icon, owner_id, features
        FROM guilds
        WHERE guilds.id = $1
        """,
            guild_id,
        )

        partial = dict(partial)

        user_perms = await base_permissions(user_id, guild_id)
        if request.discord_api_version > 7:
            partial["permissions"] = str(user_perms.binary)
        else:
            partial["permissions"] = user_perms.binary & ((2 << 31) - 1)
            partial["permissions_new"] = str(user_perms.binary)

        partial["owner"] = partial.pop("owner_id") == user_id
        partial["features"] = partial["features"] or []

        if with_counts:
            partial.update(await app.storage.get_guild_counts(guild_id))

        partials.append(partial)

    return jsonify(partials)


@bp.route("/@me/guilds/<int:guild_id>/members/@me", methods=["GET"])
async def get_guild_me(guild_id: int):
    """Get our own guild member."""
    user_id = await token_check()
    await guild_check(user_id, guild_id)

    member = await app.storage.get_member(guild_id, user_id)
    return jsonify(member)


@bp.route("/@me/guilds/<int:guild_id>", methods=["DELETE"])
async def leave_guild(guild_id: int):
    """Leave a guild."""
    user_id = await token_check()
    await guild_check(user_id, guild_id)

    await remove_member(guild_id, user_id)
    return "", 204


# @bp.route('/@me/connections', methods=['GET'])
async def get_connections():
    pass


@bp.route("/@me/consent", methods=["GET", "POST", "PATCH"])
async def get_consent():
    """Always enable data collection."""
    return jsonify(
        {
            "usage_statistics": {"consented": True},
            "personalization": {"consented": True},
        }
    )


@bp.route("/@me/harvest", methods=["GET"])
@bp.route("/@me/devices", methods=["POST"])
async def post_devices():
    """Dummy route"""
    return "", 204


@bp.route("/@me/activities/statistics/applications", methods=["GET"])
@bp.route("/@me/library", methods=["GET"])
async def get_library():
    """Probably related to Discord Store?"""
    return jsonify([])


async def map_guild_ids_to_mutual_list(
    mutual_guild_ids: List[int], peer_id: int
) -> List[dict]:
    mutual_result = []

    # ascending sorting
    for guild_id in sorted(mutual_guild_ids):
        nick = await app.db.fetchval(
            """
            SELECT nickname
            FROM members
            WHERE guild_id = $1 AND user_id = $2
            """,
            guild_id,
            peer_id,
        )

        mutual_result.append({"id": str(guild_id), "nick": nick})

    return mutual_result


@bp.route("/<int:peer_id>/profile", methods=["GET"])
async def get_profile(peer_id: int):
    """Get a user's profile."""
    user_id = await token_check()
    peer = await app.storage.get_user(peer_id)

    if not peer:
        raise NotFound(10013)

    mutual_guilds = await app.user_storage.get_mutual_guilds(user_id, peer_id)
    friends = await app.user_storage.are_friends_with(user_id, peer_id)
    staff = await is_staff(user_id)

    # don't return a proper card if no guilds are being shared (bypassed by starf)
    if not mutual_guilds and not friends and not staff:
        raise MissingAccess()

    # actual premium status is determined by that
    # column being NULL or not
    peer_premium = await app.db.fetchval(
        """
        SELECT premium_since
        FROM users
        WHERE id = $1
        """,
        peer_id,
    )

    plan_id = await app.db.fetchval(
        """
    SELECT payment_gateway_plan_id
    FROM user_subscriptions
    WHERE status = 1
        AND user_id = $1
    """,
        peer_id,
    )

    result = {
        "user": peer,
        "user_profile": peer,
        "connected_accounts": [],
        "premium_type": PLAN_ID_TO_TYPE.get(plan_id),
        "premium_since": timestamp_(peer_premium),
        "premium_guild_since": timestamp_(peer_premium),  # Same for now
        "profile_themes_experiment_bucket": 1,  # I have no words
    }

    if request.args.get("with_mutual_guilds", type=str_bool) in (None, True):
        result["mutual_guilds"] = await map_guild_ids_to_mutual_list(
            mutual_guilds, peer_id
        )

    if request.args.get("guild_id", type=int):
        guild_id = int(request.args["guild_id"])
        is_member = None
        if not staff:
            is_member = await app.storage.get_member(guild_id, user_id)
        if is_member or staff:
            member_data = await app.storage.get_member(guild_id, peer_id)
            if member_data:
                result["guild_member"] = result["guild_member_profile"] = member_data
                result["guild_member_profile"]["guild_id"] = str(guild_id)  # Husk

    if peer["bot"] and not peer["system"]:
        result["application"] = {
            "id": peer["id"],
            "flags": 8667136,
            "popular_application_command_ids": [],
            "verified": peer["flags"] & UserFlags.verified_bot
            == UserFlags.verified_bot,
        }

    return jsonify(result)


@bp.route("/@me/mentions", methods=["GET"])
async def _get_mentions():
    user_id = await token_check()

    j = validate(dict(request.args), GET_MENTIONS)

    guild_query = "AND messages.guild_id = $2" if "guild_id" in j else ""
    role_query = "OR content ILIKE '%<@&%'" if j["roles"] else ""
    everyone_query = "OR content LIKE '%@everyone%'" if j["everyone"] else ""
    mention_user = f"<@{user_id}>"

    args = [mention_user]

    if guild_query:
        args.append(j["guild_id"])

    guild_ids = await app.user_storage.get_user_guilds(user_id)
    gids = ",".join(str(guild_id) for guild_id in guild_ids)

    rows = await app.db.fetch(
        f"""
    SELECT messages.id
    FROM messages
    JOIN channels ON messages.channel_id = channels.id
    WHERE (
        channels.channel_type = 0
        AND messages.guild_id IN ({gids})
        AND content ILIKE '%'||$1||'%'
        {role_query}
        {everyone_query}
        {guild_query}
        )
    LIMIT {j["limit"]}
    """,
        *args,
    )

    res = []
    for row in rows:
        message = await app.storage.get_message(row["id"])
        gid = int(message["guild_id"])

        # ignore messages pre-messages.guild_id
        if gid not in guild_ids:
            continue

        res.append(message_view(message))

    return jsonify(res)


@bp.route("/@me/delete", methods=["POST"])
async def delete_account():
    """Delete own account.

    This removes the account from all tables and
    forces all currently connected clients to reconnect.
    """
    user_id = await token_check()

    j = await request.get_json()
    password = j.get("password", "")

    pwd_hash = await app.db.fetchval(
        """
    SELECT password_hash
    FROM users
    WHERE id = $1
    """,
        user_id,
    )
    if not await check_password(pwd_hash, password):
        raise ManualFormError(
            password={
                "code": "PASSWORD_DOES_NOT_MATCH",
                "message": "Password does not match.",
            }
        )

    owned_guilds = await app.db.fetchval(
        """
    SELECT COUNT(*)
    FROM guilds
    WHERE owner_id = $1
    """,
        user_id,
    )

    if owned_guilds > 0:
        raise BadRequest(40011)

    await delete_user(user_id)
    await user_disconnect(user_id)

    return "", 204


@bp.route("/@me/affinities/users", methods=["GET"])
async def _get_tinder_score_affinity_users():
    user_id = await token_check()

    # We make semi-accurate affinities by using relationships and private channels
    friends = await app.user_storage.get_friend_ids(user_id)
    dms = await app.user_storage.get_dms(user_id)
    dm_recipients = [
        r["id"] for dm in dms for r in dm["recipients"] if int(r["id"]) != user_id
    ]
    return jsonify(
        {
            "user_affinities": list(set(map(str, friends + dm_recipients))),
            "inverse_user_affinities": [],
        }
    )


@bp.route("/@me/affinities/guilds", methods=["GET"])
async def _get_tinder_score_affinity_guilds():
    user_id = await token_check()
    # TODO: implement this
    return jsonify({"guild_affinities": []})


@bp.route("/@me/applications/<app_id>/entitlements", methods=["GET"])
async def _stub_entitlements(app_id):
    return jsonify([])
