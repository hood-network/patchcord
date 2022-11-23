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

import re
import secrets
import datetime

from quart import Blueprint, request, current_app as app, jsonify
from logbook import Logger

from ..auth import token_check
from ..schemas import validate, INVITE
from ..enums import ChannelType
from ..errors import BadRequest, Forbidden, NotFound
from ..utils import async_map, str_bool

from litecord.blueprints.checks import (
    channel_check,
    channel_perm_check,
    guild_check,
    guild_perm_check,
)

from litecord.blueprints.dm_channels import gdm_is_member, gdm_add_recipient
from litecord.common.guilds import add_member

log = Logger(__name__)
bp = Blueprint("invites", __name__)


class UnknownInvite(NotFound):
    error_code = 10006


class AlreadyInvited(BaseException):
    pass


def gen_inv_code() -> str:
    """Generate an invite code.

    This is a primitive and does not guarantee uniqueness.
    """
    raw = secrets.token_urlsafe(10)
    raw = re.sub(r"\/|\+|\-|\_", "", raw)

    return raw[:7]


async def invite_precheck(user_id: int, guild_id: int):
    """pre-check invite use in the context of a guild."""

    joined = await app.db.fetchval(
        """
    SELECT joined_at
    FROM members
    WHERE user_id = $1 AND guild_id = $2
    """,
        user_id,
        guild_id,
    )

    if joined is not None:
        raise AlreadyInvited()

    banned = await app.db.fetchval(
        """
    SELECT reason
    FROM bans
    WHERE user_id = $1 AND guild_id = $2
    """,
        user_id,
        guild_id,
    )

    if banned is not None:
        raise UnknownInvite(40007)


async def invite_precheck_gdm(user_id: int, channel_id: int):
    """pre-checks in a group dm."""
    is_member = await gdm_is_member(channel_id, user_id)

    if is_member:
        raise AlreadyInvited()


async def _inv_check_age(inv: dict):
    delta_sec = (datetime.datetime.utcnow() - inv["created_at"]).total_seconds()

    if inv["max_age"] > 0 and delta_sec > inv["max_age"]:
        await delete_invite(inv["code"])
        raise UnknownInvite()

    if inv["max_uses"] > 0 and inv["uses"] >= inv["max_uses"]:
        await delete_invite(inv["code"])
        raise UnknownInvite()


async def use_invite(user_id, invite_code) -> bool:
    """Try using an invite"""
    inv = await app.db.fetchrow(
        """
    SELECT code, channel_id, guild_id, created_at,
           max_age, uses, max_uses
    FROM invites
    WHERE code = $1
    """,
        invite_code,
    )
    if not inv:
        raise UnknownInvite()
    await _inv_check_age(inv)

    # NOTE: if group dm invite, guild_id is null.
    guild_id = inv["guild_id"]

    try:
        if guild_id is None:
            channel_id = inv["channel_id"]
            await invite_precheck_gdm(user_id, inv["channel_id"])
            await gdm_add_recipient(channel_id, user_id)
        else:
            await invite_precheck(user_id, guild_id)
            await add_member(guild_id, user_id)

        await app.db.execute(
            """
        UPDATE invites
        SET uses = uses + 1
        WHERE code = $1
        """,
            invite_code,
        )
    except AlreadyInvited:
        return False
    else:
        return True


async def _check_max_invites(guild_id, channel_id):
    """Check that the maximum invite count (1000) isn't being blown."""
    if guild_id is not None:
        invite_count = await app.db.fetchval(
            """
            SELECT COUNT(*)
            FROM invites
            WHERE guild_id = $1
            """,
            guild_id,
        )
    else:
        invite_count = await app.db.fetchval(
            """
            SELECT COUNT(*)
            FROM invites
            WHERE channel_id = $1
            """,
            channel_id,
        )

    if invite_count >= 1000:
        raise BadRequest(30016)


@bp.route("/channels/<int:channel_id>/invites", methods=["POST"])
async def create_invite(channel_id):
    """Create an invite to a channel."""
    user_id = await token_check()
    j = validate(await request.get_json(), INVITE)

    chantype, maybe_guild_id = await channel_check(user_id, channel_id)
    chantype = ChannelType(chantype)

    # NOTE: this works on group dms, since it returns ALL_PERMISSIONS on
    # non-guild channels.
    await channel_perm_check(user_id, channel_id, "create_invites")

    if chantype == ChannelType.DM:
        raise NotFound(10003)

    invite_code = gen_inv_code()

    if chantype != ChannelType.GROUP_DM:
        guild_id = maybe_guild_id
    else:
        guild_id = None

    await _check_max_invites(guild_id, channel_id)

    await app.db.execute(
        """
        INSERT INTO invites
            (code, guild_id, channel_id, inviter, max_uses,
            max_age, temporary)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        invite_code,
        guild_id,
        channel_id,
        user_id,
        j["max_uses"],
        j["max_age"],
        j["temporary"],
    )

    invite = await _get_inv(invite_code)
    return jsonify(invite)


@bp.route("/invite/<invite_code>", methods=["GET"])
@bp.route("/invites/<invite_code>", methods=["GET"])
async def get_invite(invite_code: str):
    inv = await app.storage.get_invite(invite_code)
    if not inv:
        raise UnknownInvite()

    if request.args.get("with_counts", type=str_bool) or request.args.get("with_expiration", type=str_bool):
        extra = await app.storage.get_invite_extra(
            invite_code,
            request.args.get("with_counts", type=str_bool),
            request.args.get("with_expiration", type=str_bool),
        )
        inv.update(extra)

    return jsonify(inv)


async def delete_invite(invite_code: str):
    """Delete an invite."""
    await app.db.fetchval(
        """
    DELETE FROM invites
    WHERE code = $1
    """,
        invite_code,
    )


@bp.route("/invite/<invite_code>", methods=["DELETE"])
@bp.route("/invites/<invite_code>", methods=["DELETE"])
async def _delete_invite(invite_code: str):
    user_id = await token_check()

    guild_id = await app.db.fetchval(
        """
    SELECT guild_id
    FROM invites
    WHERE code = $1
    """,
        invite_code,
    )

    if guild_id is None:
        raise BadRequest(10006)

    await guild_perm_check(user_id, guild_id, "manage_channels")

    inv = await app.storage.get_invite(invite_code)
    await delete_invite(invite_code)
    return jsonify(inv)


async def _get_inv(code):
    inv = await app.storage.get_invite(code)
    meta = await app.storage.get_invite_metadata(code)
    return {**inv, **meta}


@bp.route("/guilds/<int:guild_id>/invites", methods=["GET"])
async def get_guild_invites(guild_id: int):
    """Get all invites for a guild."""
    user_id = await token_check()

    await guild_check(user_id, guild_id)
    await guild_perm_check(user_id, guild_id, "manage_guild")

    inv_codes = await app.db.fetch(
        """
    SELECT code
    FROM invites
    WHERE guild_id = $1
    """,
        guild_id,
    )

    inv_codes = [r["code"] for r in inv_codes]
    invs = await async_map(_get_inv, inv_codes)
    return jsonify(invs)


@bp.route("/channels/<int:channel_id>/invites", methods=["GET"])
async def get_channel_invites(channel_id: int):
    """Get all invites for a channel."""
    user_id = await token_check()

    _ctype, guild_id = await channel_check(user_id, channel_id)
    await guild_perm_check(user_id, guild_id, "manage_channels")

    inv_codes = await app.db.fetch(
        """
    SELECT code
    FROM invites
    WHERE guild_id = $1 AND channel_id = $2
    """,
        guild_id,
        channel_id,
    )

    inv_codes = [r["code"] for r in inv_codes]
    invs = await async_map(_get_inv, inv_codes)
    return jsonify(invs)


@bp.route("/invite/<invite_code>", methods=["POST"])
@bp.route("/invites/<invite_code>", methods=["POST"])
async def _use_invite(invite_code):
    """Use an invite."""
    user_id = await token_check()

    new = await use_invite(user_id, invite_code)

    inv = await app.storage.get_invite(invite_code)
    extra = await app.storage.get_invite_extra(invite_code, True, True)
    inv.update(extra)
    if new:
        inv["new_member"] = True

    return jsonify(inv)
