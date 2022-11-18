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

from quart import Blueprint, request, jsonify
from typing import TYPE_CHECKING

from litecord.blueprints.auth import token_check
from litecord.common.interop import channel_view

from litecord.errors import BadRequest, ManualFormError
from litecord.enums import ChannelType
from litecord.blueprints.guild.roles import gen_pairs

from litecord.schemas import validate, CHAN_CREATE, CHANNEL_UPDATE_POSITION
from litecord.blueprints.checks import guild_check, guild_owner_check, guild_perm_check
from litecord.common.guilds import create_guild_channel

if TYPE_CHECKING:
    from litecord.typing_hax import app, request
else:
    from quart import current_app as app, request

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

    if channel_type == ChannelType.GUILD_CATEGORY and j.get("parent_id"):
        raise ManualFormError(
            parent_id={
                "code": "CHANNEL_PARENT_INVALID_PARENT",
                "message": "Categories cannot have subcategories",
            }
        )

    if channel_type == ChannelType.GUILD_NEWS and not app.storage.has_feature(
        guild_id, "NEWS"
    ):
        raise ManualFormError(
            type={
                "code": "BASE_TYPE_CHOICES",
                "message": f"Value must be one of {CHAN_CREATE['type']['allo']}.",
            }
        )

    new_channel_id = app.winter_factory.snowflake()
    await create_guild_channel(guild_id, new_channel_id, channel_type, **j)

    chan = await app.storage.get_channel(new_channel_id)
    await app.dispatcher.guild.dispatch(guild_id, ("CHANNEL_CREATE", chan))

    return jsonify(channel_view(chan)), 201


async def _chan_update_dispatch(guild_id: int, channel_id: int):
    """Fetch new information about the channel and dispatch
    a single CHANNEL_UPDATE event to the guild."""
    chan = await app.storage.get_channel(channel_id)
    await app.dispatcher.guild.dispatch(guild_id, ("CHANNEL_UPDATE", chan))


async def _do_channel_updates(guild_id: int, updates: list):
    """Update channel positions, given the list of pairs to do.

    Dispatches CHANNEL_UPDATEs to the guild.
    """
    updated = []

    conn = await app.db.acquire()
    for pair in updates:
        _id, pos = pair

        async with conn.transaction():
            await conn.execute(
                """
            UPDATE guild_channels
            SET position = $1
            WHERE id = $2 AND guild_id = $3
            """,
                pos,
                _id,
                guild_id,
            )
        updated.append(_id)

    await app.db.release(conn)

    for _id in updated:
        await _chan_update_dispatch(guild_id, _id)


def _group_channel(chan):
    if ChannelType(chan["type"]) == ChannelType.GUILD_CATEGORY:
        return "c"
    elif chan["parent_id"] is None:
        return "n"
    return chan["parent_id"]


@bp.route("/<int:guild_id>/channels", methods=["PATCH"])
async def modify_channel_pos(guild_id):
    """Change positions of channels in a guild."""
    user_id = await token_check()

    await guild_owner_check(user_id, guild_id)
    await guild_perm_check(user_id, guild_id, "manage_channels")

    raw_j = await request.get_json()
    j = validate({"channels": raw_j}, CHANNEL_UPDATE_POSITION)
    j = j["channels"]

    channels = {
        int(chan["id"]): chan for chan in await app.storage.get_channel_data(guild_id)
    }
    channel_tree = {}

    for chan in j:
        conn = await app.db.acquire()
        _id = int(chan["id"])
        if (
            _id in channels
            and "parent_id" in chan
            and (chan["parent_id"] is None or chan["parent_id"] in channels)
        ):
            channels[_id]["parent_id"] = chan["parent_id"]
            await conn.execute(
                """
            UPDATE guild_channels
            SET parent_id = $1
            WHERE id = $2 AND guild_id = $3
            """,
                chan["parent_id"],
                chan["id"],
                guild_id,
            )

            await _chan_update_dispatch(guild_id, chan["id"])
        await app.db.release(conn)

    for chan in channels.values():
        channel_tree.setdefault(_group_channel(chan), []).append(chan)

    for _key in channel_tree:
        _channels = channel_tree[_key]
        _channel_ids = list(map(lambda chan: int(chan["id"]), _channels))
        print(_key, _channel_ids)
        _channel_positions = {chan["position"]: int(chan["id"]) for chan in _channels}
        _change_list = list(
            filter(
                lambda chan: "position" in chan and int(chan["id"]) in _channel_ids, j
            )
        )
        _swap_pairs = gen_pairs(_change_list, _channel_positions)

        await _do_channel_updates(guild_id, _swap_pairs)

    return "", 204
