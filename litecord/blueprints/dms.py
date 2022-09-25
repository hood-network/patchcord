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

"""
blueprint for direct messages
"""

from quart import Blueprint, request, current_app as app, jsonify
from logbook import Logger

from litecord.errors import Forbidden

from ..schemas import validate, CREATE_DM, CREATE_DM_V9
from ..enums import ChannelType


from .auth import token_check

from litecord.blueprints.dm_channels import gdm_create, gdm_add_recipient, gdm_pubsub
from litecord.common.channels import try_dm_state
from litecord.utils import index_by_func

log = Logger(__name__)
bp = Blueprint("dms", __name__)


@bp.route("/@me/channels", methods=["GET"])
async def get_dms():
    """Get the open DMs for the user."""
    user_id = await token_check()
    return jsonify(await app.user_storage.get_dms(user_id))


async def jsonify_dm(dm_id: int, user_id: int):
    dm_chan = await app.storage.get_dm(dm_id, user_id)
    self_user_index = index_by_func(
        lambda user: user["id"] == str(user_id), dm_chan["recipients"]
    )

    if request.discord_api_version > 7:
        assert self_user_index is not None
        dm_chan["recipients"].pop(self_user_index)
    else:
        if self_user_index == 0:
            dm_chan["recipients"].append(dm_chan["recipients"].pop(0))

    return jsonify(dm_chan)


async def create_dm(user_id: int, recipient_id: int):
    """Create a new dm with a user,
    or get the existing DM id if it already exists."""

    dm_id = await app.db.fetchval(
        """
    SELECT id
    FROM dm_channels
    WHERE (party1_id = $1 OR party2_id = $1) AND
          (party1_id = $2 OR party2_id = $2)
    """,
        user_id,
        recipient_id,
    )

    if dm_id:
        await gdm_pubsub(dm_id, (user_id, recipient_id))
        return await jsonify_dm(dm_id, user_id)

    # if no dm was found, create a new one

    dm_id = app.winter_factory.snowflake()
    await app.db.execute(
        """
    INSERT INTO channels (id, channel_type)
    VALUES ($1, $2)
    """,
        dm_id,
        ChannelType.DM.value,
    )

    await app.db.execute(
        """
    INSERT INTO dm_channels (id, party1_id, party2_id)
    VALUES ($1, $2, $3)
    """,
        dm_id,
        user_id,
        recipient_id,
    )

    # the dm state is something we use
    # to give the currently "open dms"
    # on the client.

    # we don't open a dm for the peer/recipient
    # until the user sends a message.
    await try_dm_state(user_id, dm_id)

    await gdm_pubsub(dm_id, (user_id, recipient_id))
    return await jsonify_dm(dm_id, user_id)


async def _handle_dm(user_id: int, data: dict):
    """Handle DM creation requests."""

    if "recipient_ids" in data:
        j = validate(data, CREATE_DM)
    else:
        j = validate(data, CREATE_DM_V9)

    recipients = j.get("recipient_ids", j["recipients"])
    if len(recipients) > 1:
        channel_id = await gdm_create(user_id, int(recipients[0]))
        for recipient in recipients[1:]:
            await gdm_add_recipient(channel_id, int(recipient))
        return jsonify(await app.storage.get_channel(channel_id, user_id=user_id))

    return await create_dm(user_id, int(recipients[0]))


@bp.route("/@me/channels", methods=["POST"])
async def start_dm():
    """Create a DM with a user."""
    user_id = await token_check()
    return await _handle_dm(user_id, await request.get_json())


@bp.route("/<int:p_user_id>/channels", methods=["POST"])
async def create_group_dm(p_user_id: int):
    """Create a DM or a Group DM with user(s)."""
    user_id = await token_check()
    if user_id != p_user_id:
        raise Forbidden('Cannot create a private channel for another user')

    return await _handle_dm(user_id, await request.get_json())
