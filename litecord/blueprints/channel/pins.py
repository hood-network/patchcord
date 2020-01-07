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

from quart import Blueprint, current_app as app, jsonify

from litecord.auth import token_check
from litecord.blueprints.checks import channel_check, channel_perm_check
from winter import snowflake_datetime
from litecord.types import timestamp_

from litecord.system_messages import send_sys_message
from litecord.enums import MessageType, SYS_MESSAGES
from litecord.errors import BadRequest

bp = Blueprint("channel_pins", __name__)


class SysMsgInvalidAction(BadRequest):
    """Invalid action on a system message."""

    error_code = 50021


@bp.route("/<int:channel_id>/pins", methods=["GET"])
async def get_pins(channel_id):
    """Get the pins for a channel"""
    user_id = await token_check()
    await channel_check(user_id, channel_id)

    ids = await app.db.fetch(
        """
    SELECT message_id
    FROM channel_pins
    WHERE channel_id = $1
    ORDER BY message_id DESC
    """,
        channel_id,
    )

    ids = [r["message_id"] for r in ids]
    res = []

    for message_id in ids:
        message = await app.storage.get_message(message_id)
        if message is not None:
            res.append(message)

    return jsonify(res)


@bp.route("/<int:channel_id>/pins/<int:message_id>", methods=["PUT"])
async def add_pin(channel_id, message_id):
    """Add a pin to a channel"""
    user_id = await token_check()
    _ctype, guild_id = await channel_check(user_id, channel_id)

    await channel_perm_check(user_id, channel_id, "manage_messages")

    mtype = await app.db.fetchval(
        """
    SELECT message_type
    FROM messages
    WHERE id = $1
    """,
        message_id,
    )

    if mtype in SYS_MESSAGES:
        raise SysMsgInvalidAction("Cannot execute action on a system message")

    await app.db.execute(
        """
    INSERT INTO channel_pins (channel_id, message_id)
    VALUES ($1, $2)
    """,
        channel_id,
        message_id,
    )

    row = await app.db.fetchrow(
        """
    SELECT message_id
    FROM channel_pins
    WHERE channel_id = $1
    ORDER BY message_id ASC
    LIMIT 1
    """,
        channel_id,
    )

    timestamp = snowflake_datetime(row["message_id"])

    await app.dispatcher.dispatch(
        "channel",
        channel_id,
        "CHANNEL_PINS_UPDATE",
        {"channel_id": str(channel_id), "last_pin_timestamp": timestamp_(timestamp)},
    )

    await send_sys_message(
        app, channel_id, MessageType.CHANNEL_PINNED_MESSAGE, message_id, user_id
    )

    return "", 204


@bp.route("/<int:channel_id>/pins/<int:message_id>", methods=["DELETE"])
async def delete_pin(channel_id, message_id):
    user_id = await token_check()
    _ctype, guild_id = await channel_check(user_id, channel_id)

    await channel_perm_check(user_id, channel_id, "manage_messages")

    await app.db.execute(
        """
    DELETE FROM channel_pins
    WHERE channel_id = $1 AND message_id = $2
    """,
        channel_id,
        message_id,
    )

    row = await app.db.fetchrow(
        """
    SELECT message_id
    FROM channel_pins
    WHERE channel_id = $1
    ORDER BY message_id ASC
    LIMIT 1
    """,
        channel_id,
    )

    timestamp = snowflake_datetime(row["message_id"])

    await app.dispatcher.dispatch(
        "channel",
        channel_id,
        "CHANNEL_PINS_UPDATE",
        {"channel_id": str(channel_id), "last_pin_timestamp": timestamp.isoformat()},
    )

    return "", 204
