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

from quart import Blueprint, request, current_app as app, jsonify

from litecord.blueprints.auth import token_check

from litecord.errors import BadRequest
from litecord.enums import ChannelType
from litecord.blueprints.guild.roles import gen_pairs

from litecord.schemas import validate, ROLE_UPDATE_POSITION, CHAN_CREATE
from litecord.blueprints.checks import guild_check, guild_owner_check, guild_perm_check
from litecord.common.guilds import create_guild_channel

bp = Blueprint("guild_channels", __name__)


@bp.route("/<int:guild_id>/channels", methods=["GET"])
async def get_guild_channels(guild_id):
    """Get the list of channels in a guild."""
    user_id = await token_check()
    await guild_check(user_id, guild_id)

    return jsonify(await app.storage.get_channel_data(guild_id))


@bp.route("/<int:guild_id>/channels", methods=["POST"])
async def create_channel(guild_id):
    """Create a channel in a guild."""
    user_id = await token_check()
    j = validate(await request.get_json(), CHAN_CREATE)

    await guild_check(user_id, guild_id)
    await guild_perm_check(user_id, guild_id, "manage_channels")

    channel_type = j.get("type", ChannelType.GUILD_TEXT)
    channel_type = ChannelType(channel_type)

    if channel_type not in (ChannelType.GUILD_TEXT, ChannelType.GUILD_VOICE):
        raise BadRequest("Invalid channel type")

    new_channel_id = app.winter_factory.snowflake()
    await create_guild_channel(guild_id, new_channel_id, channel_type, **j)

    chan = await app.storage.get_channel(new_channel_id)
    await app.dispatcher.guild.dispatch(guild_id, ("CHANNEL_CREATE", chan))

    return jsonify(chan), 201


async def _chan_update_dispatch(guild_id: int, channel_id: int):
    """Fetch new information about the channel and dispatch
    a single CHANNEL_UPDATE event to the guild."""
    chan = await app.storage.get_channel(channel_id)
    await app.dispatcher.guild.dispatch(guild_id, ("CHANNEL_UPDATE", chan))


async def _do_single_swap(guild_id: int, pair: tuple):
    """Do a single channel swap, dispatching
    the CHANNEL_UPDATE events for after the swap"""
    pair1, pair2 = pair
    channel_1, new_pos_1 = pair1
    channel_2, new_pos_2 = pair2

    # do the swap in a transaction.
    conn = await app.db.acquire()

    async with conn.transaction():
        await conn.executemany(
            """
        UPDATE guild_channels
        SET position = $1
        WHERE id = $2 AND guild_id = $3
        """,
            [(new_pos_1, channel_1, guild_id), (new_pos_2, channel_2, guild_id)],
        )

    await app.db.release(conn)

    await _chan_update_dispatch(guild_id, channel_1)
    await _chan_update_dispatch(guild_id, channel_2)


async def _do_channel_swaps(guild_id: int, swap_pairs: list):
    """Swap channel pairs' positions, given the list
    of pairs to do.

    Dispatches CHANNEL_UPDATEs to the guild.
    """
    for pair in swap_pairs:
        await _do_single_swap(guild_id, pair)


@bp.route("/<int:guild_id>/channels", methods=["PATCH"])
async def modify_channel_pos(guild_id):
    """Change positions of channels in a guild."""
    user_id = await token_check()

    await guild_owner_check(user_id, guild_id)
    await guild_perm_check(user_id, guild_id, "manage_channels")

    # same thing as guild.roles, so we use
    # the same schema and all.
    raw_j = await request.get_json()
    j = validate({"roles": raw_j}, ROLE_UPDATE_POSITION)
    roles = j["roles"]

    channels = await app.storage.get_channel_data(guild_id)

    channel_positions = {chan["position"]: int(chan["id"]) for chan in channels}
    swap_pairs = gen_pairs(roles, channel_positions)
    await _do_channel_swaps(guild_id, swap_pairs)
    return "", 204
