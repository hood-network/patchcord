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

from litecord.auth import token_check
from litecord.blueprints.checks import channel_check, channel_perm_check
from litecord.types import timestamp_

from litecord.system_messages import send_sys_message
from litecord.enums import MessageType, SYS_MESSAGES
from litecord.errors import BadRequest
from litecord.common.interop import message_view

if TYPE_CHECKING:
    from litecord.typing_hax import app, request
else:
    from quart import current_app as app, request

bp = Blueprint("channel_pins", __name__)


async def _dispatch_pins_update(channel_id: int) -> None:
    message_id = await app.db.fetchval(
        """
        SELECT message_id
        FROM channel_pins
        WHERE channel_id = $1
        ORDER BY message_id ASC
        LIMIT 1
        """,
        channel_id,
    )

    timestamp = (
        app.winter_factory.to_datetime(message_id) if message_id is not None else None
    )
    await app.dispatcher.channel.dispatch(
        channel_id,
        (
            "CHANNEL_PINS_UPDATE",
            {
                "channel_id": str(channel_id),
                "last_pin_timestamp": timestamp_(timestamp),
            },
        ),
    )


@bp.route("/<int:channel_id>/pins", methods=["GET"])
async def get_pins(channel_id):
    """Get the pins for a channel"""
    user_id = await token_check()
    await channel_check(user_id, channel_id)

    # TODO: proper ordering
    messages = await app.storage.get_messages(
        user_id=user_id,
        where_clause="""
            WHERE channel_id = $1 AND NOT (pinned = NULL)
            ORDER BY message_id DESC
        """,
        args=(channel_id,),
    )

    return jsonify([message_view(message) for message in messages])


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
        raise BadRequest(50021)

    await app.db.execute(
        """
    INSERT INTO channel_pins (channel_id, message_id)
    VALUES ($1, $2)
    """,
        channel_id,
        message_id,
    )

    await _dispatch_pins_update(channel_id)

    await send_sys_message(
        channel_id, MessageType.CHANNEL_PINNED_MESSAGE, message_id, user_id
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

    await _dispatch_pins_update(channel_id)

    return "", 204
