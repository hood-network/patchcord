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
from litecord.auth import token_check
from litecord.common.channels import channel_ack
from litecord.errors import GuildNotFound
from litecord.blueprints.checks import channel_check, guild_check
from litecord.schemas import validate, BULK_ACK
from litecord.enums import GUILD_CHANS


bp = Blueprint("read_states", __name__)


@bp.route("/channels/<int:channel_id>/messages/<int:message_id>/ack", methods=["POST"])
async def ack_channel(channel_id, message_id):
    """Acknowledge a channel."""
    user_id = await token_check()
    ctype, guild_id = await channel_check(user_id, channel_id)

    if ctype not in GUILD_CHANS:
        guild_id = None

    await channel_ack(user_id, channel_id, guild_id, message_id)

    return jsonify(
        {
            # token seems to be used for
            # data collection activities,
            # so we never use it.
            "token": None
        }
    )


@bp.route("/read-states/ack-bulk", methods=["POST"])
async def bulk_ack():
    """Acknowledge multiple channels in a row"""
    user_id = await token_check()
    j = validate(await request.get_json(), BULK_ACK)
    for ack_request in j:
        channel_id, message_id = ack_request["channel_id"], ack_request["message_id"]
        ctype, guild_id = await channel_check(user_id, channel_id)
        if ctype not in GUILD_CHANS:
            guild_id = None

        await channel_ack(user_id, channel_id, guild_id, message_id)

    # TODO: validate if this is the correct response
    return "", 204


@bp.route("/channels/<int:channel_id>/messages/ack", methods=["DELETE"])
async def delete_read_state(channel_id):
    """Delete the read state of a channel."""
    user_id = await token_check()
    try:
        await channel_check(user_id, channel_id)
    except GuildNotFound:
        # ignore when guild isn't found because we're deleting the
        # read state regardless.
        pass

    await app.db.execute(
        """
    DELETE FROM user_read_state
    WHERE user_id = $1 AND channel_id = $2
    """,
        user_id,
        channel_id,
    )

    return "", 204


@bp.route("/guilds/<int:guild_id>/ack", methods=["POST"])
async def ack_guild(guild_id):
    """ACKnowledge all messages in the guild."""
    user_id = await token_check()
    await guild_check(user_id, guild_id)

    chan_ids = await app.storage.get_channel_ids(guild_id)

    for chan_id in chan_ids:
        await channel_ack(user_id, chan_id, guild_id)

    return "", 204
