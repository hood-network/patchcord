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

from typing import List

from asyncpg import UniqueViolationError
from quart import Blueprint, jsonify, request, current_app as app
from logbook import Logger

from ..errors import Forbidden, BadRequest, Unauthorized
from ..schemas import validate, USER_UPDATE, GET_MENTIONS

from .guilds import guild_check
from litecord.auth import token_check, hash_data
from litecord.common.guilds import remove_member

from litecord.enums import PremiumType
from litecord.images import parse_data_uri
from litecord.permissions import base_permissions

from litecord.blueprints.auth import check_password
from litecord.utils import to_update
from litecord.common.messages import message_view
from litecord.common.users import (
    mass_user_update,
    delete_user,
    check_username_usage,
    roll_discrim,
    user_disconnect,
)

bp = Blueprint("user", __name__)
log = Logger(__name__)


@bp.route("/@me", methods=["GET"])
async def get_me():
    """Get the current user's information."""
    user_id = await token_check()
    user = await app.storage.get_user(user_id, True)
    return jsonify(user)


@bp.route("/<int:target_id>", methods=["GET"])
async def get_other(target_id):
    """Get any user, given the user ID."""
    user_id = await token_check()

    bot = await app.db.fetchval(
        """
    SELECT bot FROM users
    WHERE users.id = $1
    """,
        user_id,
    )

    if not bot:
        raise Forbidden("Only bots can use this endpoint")

    other = await app.storage.get_user(target_id)
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
            raise BadRequest(
                "Unable to change username",
                {"username": "Too many people are with this username."},
            )

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
        raise BadRequest(
            "Invalid discriminator",
            {"discriminator": "Someone already used this discriminator."},
        )


async def _check_pass(j, user):
    # Do not do password checks on unclaimed accounts
    if user["email"] is None:
        return

    if not j["password"]:
        raise BadRequest("password required", {"password": "password required"})

    phash = user["password_hash"]

    if not await check_password(phash, j["password"]):
        raise BadRequest("password incorrect", {"password": "password does not match."})


@bp.route("/@me", methods=["PATCH"])
async def patch_me():
    """Patch the current user's information."""
    user_id = await token_check()

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
        # this will take care of regenning a new discriminator
        discrim = await _try_username_patch(user_id, j["username"])
        user["username"] = j["username"]
        user["discriminator"] = discrim

    if to_update(j, user, "discriminator"):
        # the API treats discriminators as integers,
        # but I work with strings on the database.
        new_discrim = str(j["discriminator"])

        await _try_discrim_patch(user_id, new_discrim)
        user["discriminator"] = new_discrim

    if to_update(j, user, "email"):
        await _check_pass(j, user)

        # TODO: reverify the new email?
        await app.db.execute(
            """
        UPDATE users
        SET email = $1
        WHERE id = $2
        """,
            j["email"],
            user_id,
        )
        user["email"] = j["email"]

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

        if mime == "image/gif" and user["premium_type"] == PremiumType.NONE:
            raise BadRequest("no gif without nitro")

        new_icon = await app.icons.update("user", user_id, j["avatar"], size=(128, 128))

        await app.db.execute(
            """
        UPDATE users
        SET avatar = $1
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
            j["bio"],
            user_id,
        )

    if to_update(j, user, "accent_color"):
        await app.db.execute(
            """
            UPDATE users
            SET accent_color = $1
            WHERE id = $2
            """,
            j["accent_color"],
            user_id,
        )

    if user["email"] is None and "new_password" not in j:
        raise BadRequest("missing password", {"password": "Please set a password."})

    if "new_password" in j and j["new_password"]:
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

    user.pop("password_hash")

    _, private_user = await mass_user_update(user_id)
    return jsonify(private_user)


@bp.route("/@me/guilds", methods=["GET"])
async def get_me_guilds():
    """Get partial user guilds."""
    user_id = await token_check()
    guild_ids = await app.user_storage.get_user_guilds(user_id)

    partials = []

    for guild_id in guild_ids:
        partial = await app.db.fetchrow(
            """
        SELECT id::text, name, icon, owner_id
        FROM guilds
        WHERE guilds.id = $1
        """,
            guild_id,
        )

        partial = dict(partial)

        user_perms = await base_permissions(user_id, guild_id)
        partial["permissions"] = user_perms.binary

        partial["owner"] = partial["owner_id"] == user_id

        partial.pop("owner_id")

        partials.append(partial)

    return jsonify(partials)


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


@bp.route("/@me/consent", methods=["GET", "POST"])
async def get_consent():
    """Always disable data collection.

    Also takes any data collection changes
    by the client and ignores them, as they
    will always be false.
    """
    return jsonify(
        {
            "usage_statistics": {"consented": False},
            "personalization": {"consented": False},
        }
    )


@bp.route("/@me/harvest", methods=["GET"])
async def get_harvest():
    """Dummy route"""
    return "", 204


@bp.route("/@me/devices", methods=["POST"])
async def post_devices():
    """Dummy route"""
    return "", 204


@bp.route("/@me/activities/statistics/applications", methods=["GET"])
async def get_stats_applications():
    """Dummy route for info on gameplay time and such"""
    return jsonify([])


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
        return "", 404

    mutual_guilds = await app.user_storage.get_mutual_guilds(user_id, peer_id)
    friends = await app.user_storage.are_friends_with(user_id, peer_id)

    # don't return a proper card if no guilds are being shared.
    if not mutual_guilds and not friends:
        return "", 404

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

    result = {
        "user": peer,
        "connected_accounts": [],
        "premium_since": peer_premium,
    }

    if request.args.get("with_mutual_guilds", type=bool) in (None, True):
        result["mutual_guilds"] = await map_guild_ids_to_mutual_list(
            mutual_guilds, peer_id
        )

    return jsonify(result)


@bp.route("/@me/mentions", methods=["GET"])
async def _get_mentions():
    user_id = await token_check()

    j = validate(dict(request.args), GET_MENTIONS)

    guild_query = "AND messages.guild_id = $2" if "guild_id" in j else ""
    role_query = "OR content LIKE '%<@&%'" if j["roles"] else ""
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
        AND content LIKE '%'||$1||'%'
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

    try:
        password = j["password"]
    except KeyError:
        raise BadRequest("password required")

    owned_guilds = await app.db.fetchval(
        """
    SELECT COUNT(*)
    FROM guilds
    WHERE owner_id = $1
    """,
        user_id,
    )

    if owned_guilds > 0:
        raise BadRequest("You still own guilds.")

    pwd_hash = await app.db.fetchval(
        """
    SELECT password_hash
    FROM users
    WHERE id = $1
    """,
        user_id,
    )

    if not await check_password(pwd_hash, password):
        raise Unauthorized("password does not match")

    await delete_user(user_id)
    await user_disconnect(user_id)

    return "", 204


@bp.route("/@me/affinities/users", methods=["GET"])
async def _get_tinder_score_affinity_users():
    return {"user_affinities": []}


@bp.route("/@me/affinities/guilds", methods=["GET"])
async def _get_tinder_score_affinity_guilds():
    return {"guild_affinities": []}


@bp.route("/@me/applications/521842831262875670/entitlements", methods=["GET"])
async def _stub_entitlements():
    return []
