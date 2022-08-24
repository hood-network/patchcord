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

import secrets
import time
from typing import List, Optional

from quart import Blueprint, request, current_app as app, jsonify
from logbook import Logger

from litecord.auth import token_check
from litecord.common.interop import message_view, channel_view
from litecord.common.guilds import process_overwrites, _dispatch_action
from litecord.enums import ChannelType, GUILD_CHANS, MessageType, MessageFlags
from litecord.errors import Forbidden, NotFound, BadRequest, MissingPermissions
from litecord.schemas import (
    maybebool,
    validate,
    CHAN_UPDATE,
    CHAN_OVERWRITE,
    GROUP_DM_UPDATE,
    BULK_DELETE,
    FOLLOW_CHANNEL,
    USER_MENTION,
)

from litecord.blueprints.checks import channel_check, channel_perm_check
from litecord.system_messages import send_sys_message
from litecord.blueprints.dm_channels import gdm_is_member, gdm_is_owner, gdm_remove_recipient, gdm_destroy
from litecord.utils import str_bool, to_update, pg_set_json
from litecord.embed.messages import process_url_embed, msg_update_embeds
from litecord.pubsub.user import dispatch_user
from litecord.permissions import get_permissions, Target

from .channel.messages import _del_msg_fkeys
from .webhooks import _dispatch_webhook_update
from .guilds import handle_search

log = Logger(__name__)
bp = Blueprint("channels", __name__)


@bp.route("/<int:channel_id>", methods=["GET"])
async def get_channel(channel_id):
    """Get a single channel's information"""
    user_id = await token_check()

    # channel_check takes care of checking
    # DMs and group DMs
    await channel_check(user_id, channel_id)
    chan = await app.storage.get_channel(channel_id, user_id=user_id)

    if not chan:
        raise NotFound(10003)

    return jsonify(channel_view(chan))


async def __guild_chan_sql(guild_id, channel_id, field: str) -> str:
    """Update a guild's channel id field to NULL,
    if it was set to the given channel id before."""
    return await app.db.execute(
        f"""
    UPDATE guilds
    SET {field} = NULL
    WHERE guilds.id = $1 AND {field} = $2
    """,
        guild_id,
        channel_id,
    )


async def _update_guild_chan_text(guild_id: int, channel_id: int):
    res_embed = await __guild_chan_sql(guild_id, channel_id, "embed_channel_id")
    res_widget = await __guild_chan_sql(guild_id, channel_id, "widget_channel_id")
    res_system = await __guild_chan_sql(guild_id, channel_id, "system_channel_id")

    # if none of them were actually updated,
    # ignore and dont dispatch anything
    if "UPDATE 1" not in (res_embed, res_widget, res_system):
        return

    # at least one of the fields were updated,
    # dispatch GUILD_UPDATE
    guild = await app.storage.get_guild_full(guild_id)
    await app.dispatcher.guild.dispatch(guild_id, ("GUILD_UPDATE", guild))


async def _update_guild_chan_voice(guild_id: int, channel_id: int):
    res = await __guild_chan_sql(guild_id, channel_id, "afk_channel_id")

    # guild didnt update
    if res == "UPDATE 0":
        return

    guild = await app.storage.get_guild_full(guild_id)
    await app.dispatcher.dispatch(guild_id, ("GUILD_UPDATE", guild))


async def _update_guild_chan_cat(guild_id: int, channel_id: int):
    # get all channels that were childs of the category
    childs = await app.db.fetch(
        """
    SELECT id
    FROM guild_channels
    WHERE guild_id = $1 AND parent_id = $2
    """,
        guild_id,
        channel_id,
    )
    childs = [c["id"] for c in childs]

    # update every child channel to parent_id = NULL
    await app.db.execute(
        """
    UPDATE guild_channels
    SET parent_id = NULL
    WHERE guild_id = $1 AND parent_id = $2
    """,
        guild_id,
        channel_id,
    )

    # tell all people in the guild of the category removal
    for child_id in childs:
        child = await app.storage.get_channel(child_id)
        await app.dispatcher.guild.dispatch(guild_id, ("CHANNEL_UPDATE", child))


async def _delete_messages(channel_id):
    await app.db.execute(
        """
    DELETE FROM channel_pins
    WHERE channel_id = $1
    """,
        channel_id,
    )

    await app.db.execute(
        """
    DELETE FROM user_read_state
    WHERE channel_id = $1
    """,
        channel_id,
    )

    ids = await app.db.fetch(
        """
    SELECT id
    FROM messages
    WHERE channel_id = $1
    """,
        channel_id,
    )
    for id in ids:
        await _del_msg_fkeys(id["id"], channel_id)
    await app.db.execute(
        """
    DELETE FROM messages
    WHERE channel_id = $1
    """,
        channel_id,
    )


async def _guild_cleanup(channel_id):
    await app.db.execute(
        """
    DELETE FROM channel_overwrites
    WHERE channel_id = $1
    """,
        channel_id,
    )

    await app.db.execute(
        """
    DELETE FROM invites
    WHERE channel_id = $1
    """,
        channel_id,
    )

    await app.db.execute(
        """
    DELETE FROM webhooks
    WHERE channel_id = $1
    """,
        channel_id,
    )


@bp.route("/<int:channel_id>", methods=["DELETE"])
async def close_channel(channel_id):
    """Close or delete a channel."""
    user_id = await token_check()

    chan_type = await app.storage.get_chan_type(channel_id)
    if chan_type is None:
        raise NotFound(10003)

    ctype = ChannelType(chan_type)

    if ctype in GUILD_CHANS:
        _, guild_id = await channel_check(user_id, channel_id)
        await channel_perm_check(user_id, channel_id, "manage_channels")
        chan = await app.storage.get_channel(channel_id, user_id=user_id)

        # the selected function will take care of checking
        # the sanity of tables once the channel becomes deleted.
        _update_func = {
            ChannelType.GUILD_TEXT: _update_guild_chan_text,
            ChannelType.GUILD_VOICE: _update_guild_chan_voice,
            ChannelType.GUILD_CATEGORY: _update_guild_chan_cat,
            ChannelType.GUILD_NEWS: _update_guild_chan_text,
        }[ctype]

        main_tbl = {
            ChannelType.GUILD_TEXT: "guild_text_channels",
            ChannelType.GUILD_VOICE: "guild_voice_channels",
            ChannelType.GUILD_CATEGORY: None,
            ChannelType.GUILD_NEWS: "guild_text_channels",
        }[ctype]

        await _update_func(guild_id, channel_id)

        # for some reason ON DELETE CASCADE
        # didn't work on my setup, so I delete
        # everything before moving to the main
        # channel table deletes
        await _delete_messages(channel_id)
        await _guild_cleanup(channel_id)

        if main_tbl is not None:
            await app.db.execute(
                f"""
            DELETE FROM {main_tbl}
            WHERE id = $1
            """,
                channel_id
            )

        updated_ids = []
        if ctype == ChannelType.GUILD_CATEGORY:
            rows = await app.db.fetch(
                """
            SELECT id
            FROM guild_channels
            WHERE parent_id = $1
            """,
                channel_id,
            )
            updated_ids = [r["id"] for r in rows]

            await app.db.execute(
                """
            UPDATE guild_channels SET parent_id = NULL
            WHERE parent_id = $1
            """,
                channel_id
            )

        await app.db.execute(
            """
        DELETE FROM guild_channels
        WHERE id = $1
        """,
            channel_id,
        )

        await app.db.execute(
            """
        DELETE FROM channels
        WHERE id = $1
        """,
            channel_id,
        )

        # clean its member list representation
        app.lazy_guild.remove_channel(channel_id)

        await app.dispatcher.guild.dispatch(guild_id, ("CHANNEL_DELETE", chan))
        for id in updated_ids:
            channel = await app.storage.get_channel(id)
            await app.dispatcher.guild.dispatch(guild_id, ("CHANNEL_UPDATE", channel))

        await app.dispatcher.channel.drop(channel_id)
        return jsonify(channel_view(chan))
    elif ctype == ChannelType.DM:
        chan = await app.storage.get_channel(channel_id)

        # we don't ever actually delete DM channels off the database.
        # instead, we close the channel for the user that is making
        # the request via removing the link between them and
        # the channel on dm_channel_state
        await app.db.execute(
            """
        DELETE FROM dm_channel_state
        WHERE user_id = $1 AND dm_id = $2
        """,
            user_id,
            channel_id,
        )

        # nothing happens to the other party of the dm channel
        await app.dispatcher.channel.unsub(channel_id, user_id)
        await dispatch_user(user_id, ("CHANNEL_DELETE", chan))

        return jsonify(chan)
    elif ctype == ChannelType.GROUP_DM:
        silent = request.args.get("silent", type=str_bool)
        await gdm_remove_recipient(channel_id, user_id, silent)
        chan = await app.storage.get_channel(channel_id, user_id=user_id)

        gdm_count = await app.db.fetchval(
            """
        SELECT COUNT(*)
        FROM group_dm_members
        WHERE id = $1
        """,
            channel_id,
        )

        if gdm_count == 0:
            await gdm_destroy(channel_id)
        else:
            # We transfer ownership to the first member in the group
            if chan["owner_id"] in (None, str(user_id)):
                await app.db.execute(
                    """
                UPDATE group_dm_channels
                SET owner_id = $1
                WHERE id = $2
                """,
                    int(chan["recipients"][0]["id"]),
                    channel_id,
                )

                chan = await app.storage.get_channel(channel_id, user_id=user_id)
                await app.dispatcher.channel.dispatch(channel_id, ("CHANNEL_UPDATE", chan))

        return jsonify(chan)
    else:
        raise RuntimeError(f"Data inconsistency: Unknown channel type {ctype}")


async def _update_pos(channel_id, pos: int):
    await app.db.execute(
        """
    UPDATE guild_channels
    SET position = $1
    WHERE id = $2
    """,
        pos,
        channel_id,
    )


async def _mass_chan_update(guild_id, channel_ids: List[Optional[int]]):
    for channel_id in channel_ids:
        if channel_id is None:
            continue

        chan = await app.storage.get_channel(channel_id)
        await app.dispatcher.guild.dispatch(guild_id, ("CHANNEL_UPDATE", chan))


@bp.route("/<int:channel_id>/permissions/<int:overwrite_id>", methods=["PUT"])
async def put_channel_overwrite(channel_id: int, overwrite_id: int):
    """Insert or modify a channel overwrite."""
    user_id = await token_check()
    ctype, guild_id = await channel_check(user_id, channel_id)

    if ctype not in GUILD_CHANS:
        raise Forbidden(50003)

    await channel_perm_check(user_id, guild_id, "manage_roles")

    j = validate(
        # inserting a fake id on the payload so validation passes through
        {**await request.get_json(), **{"id": -1}},
        CHAN_OVERWRITE,
    )

    await process_overwrites(
        guild_id,
        channel_id,
        [
            {
                "allow": j["allow"],
                "deny": j["deny"],
                "type": j["type"],
                "id": overwrite_id,
            }
        ],
    )

    await _mass_chan_update(guild_id, [channel_id])
    return "", 204


@bp.route("/<int:channel_id>/permissions/<int:overwrite_id>", methods=["DELETE"])
async def delete_channel_overwrite(channel_id: int, overwrite_id: int):
    """Delete a channel overwrite."""
    user_id = await token_check()
    ctype, guild_id = await channel_check(user_id, channel_id)

    if ctype not in GUILD_CHANS:
        raise Forbidden(50003)

    await channel_perm_check(user_id, guild_id, "manage_roles")

    target_type = await app.db.fetchval(
        """
    SELECT target_type
    FROM channel_overwrites
    WHERE channel_id = $1 AND (target_user = $2 OR target_role = $2)
        """,
        channel_id,
        overwrite_id,
    )
    if not target_type:
        return "", 204

    target = Target(target_type, overwrite_id, overwrite_id)
    col_name = "target_user" if target.is_user else "target_role"

    await app.db.execute(
        f"""
    DELETE FROM channel_overwrites
    WHERE channel_id = $1 AND {col_name} = $2
        """,
        channel_id,
        overwrite_id,
    )

    user_ids = []
    if target.is_user:
        user_ids.append(target.user_id)
    elif target.is_role:
        user_ids.extend(await app.storage.get_role_members(target.role_id))

    for user_id in user_ids:
        perms = await get_permissions(user_id, channel_id)
        await _dispatch_action(guild_id, channel_id, user_id, perms)

    await _mass_chan_update(guild_id, [channel_id])
    return "", 204


async def _update_channel_common(channel_id: int, guild_id: int, j: dict):
    chan = await app.storage.get_channel(channel_id)

    if "name" in j:
        await app.db.execute(
            """
            UPDATE guild_channels
            SET name = $1
            WHERE id = $2
            """,
            j["name"],
            channel_id,
        )

    if to_update(j, chan, "banner"):
        new_icon = await app.icons.update("channel_banner", channel_id, j["banner"])

        await app.db.execute(
            """
        UPDATE guild_channels
        SET banner = $1
        WHERE id = $2
        """,
            new_icon.icon_hash,
            channel_id,
        )

    if "position" in j:
        channel_data = await app.storage.get_channel_data(guild_id)
        # get an ordered list of the chans array by position
        # TODO bad impl. can break easily. maybe dict?
        chans: List[Optional[int]] = [None] * len(channel_data)
        for chandata in channel_data:
            chans.insert(chandata["position"], int(chandata["id"]))

        # are we changing to the left or to the right?

        # left: [channel1, channel2, ..., channelN-1, channelN]
        #       becomes
        #       [channel1, channelN-1, channel2, ..., channelN]
        #       so we can say that the "main change" is
        #       channelN-1 going to the position channel2
        #       was occupying.
        current_pos = chans.index(channel_id)
        new_pos = j["position"]

        # if the new position is bigger than the current one,
        # we're making a left shift of all the channels that are
        # beyond the current one, to make space
        left_shift = new_pos > current_pos

        # find all channels that we'll have to shift
        shift_block: List[Optional[int]] = (
            chans[current_pos:new_pos] if left_shift else chans[new_pos:current_pos]
        )

        shift = -1 if left_shift else 1

        # do the shift (to the left or to the right)
        await app.db.executemany(
            """
        UPDATE guild_channels
        SET position = position + $1
        WHERE id = $2
        """,
            [(shift, chan_id) for chan_id in shift_block],
        )

        await _mass_chan_update(guild_id, shift_block)

        # since theres now an empty slot, move current channel to it
        await _update_pos(channel_id, new_pos)

    if "channel_overwrites" in j:
        overwrites = j["channel_overwrites"]
        await process_overwrites(guild_id, channel_id, overwrites)


async def _common_guild_chan(channel_id, j: dict):
    # common updates to the guild_channels table
    for field in [field for field in j.keys() if field in ("nsfw", "parent_id")]:
        await app.db.execute(
            f"""
        UPDATE guild_channels
        SET {field} = $1
        WHERE id = $2
        """,
            j[field],
            channel_id,
        )


async def _update_text_channel(channel_id: int, j: dict, _user_id: int):
    channel = await app.storage.get_channel(channel_id)

    # first do the specific ones related to guild_text_channels
    for field in [
        field for field in j.keys() if field in ("topic", "rate_limit_per_user")
    ]:
        await app.db.execute(
            f"""
        UPDATE guild_text_channels
        SET {field} = $1
        WHERE id = $2
        """,
            j[field],
            channel_id,
        )

    if channel["type"] in (ChannelType.GUILD_TEXT.value, ChannelType.GUILD_NEWS.value) and j["type"] in (ChannelType.GUILD_TEXT.value, ChannelType.GUILD_NEWS.value):
        await app.db.execute(
            f"""
        UPDATE channels
        SET channel_type = $1
        WHERE id = $2
        """,
            j["type"],
            channel_id,
        )

        await app.db.execute(
            f"""
        DELETE FROM webhooks
        WHERE (channel_id = $1 OR source_id = $1)
        """,
            channel_id,
        )

    await _common_guild_chan(channel_id, j)


async def _update_voice_channel(channel_id: int, j: dict, _user_id: int):
    # first do the specific ones in guild_voice_channels
    for field in [field for field in j.keys() if field in ("bitrate", "user_limit")]:
        await app.db.execute(
            f"""
        UPDATE guild_voice_channels
        SET {field} = $1
        WHERE id = $2
        """,
            j[field],
            channel_id,
        )

    # yes, i'm letting voice channels have nsfw, you cant stop me
    await _common_guild_chan(channel_id, j)


async def _update_group_dm(channel_id: int, j: dict, author_id: int):
    if "name" in j:
        await gdm_is_owner(channel_id, author_id)

        await app.db.execute(
            """
        UPDATE group_dm_channels
        SET name = $1
        WHERE id = $2
        """,
            j["name"],
            channel_id,
        )

        await send_sys_message(channel_id, MessageType.CHANNEL_NAME_CHANGE, author_id)

    if j.get("owner"):
        await gdm_is_owner(channel_id, author_id)

        await app.db.execute(
            """
        UPDATE group_dm_channels
        SET owner_id = $1
        WHERE id = $2
        """,
            j["owner"],
            channel_id,
        )

    if "icon" in j:
        new_icon = await app.icons.update(
            "channel_icon", channel_id, j["icon"], always_icon=True
        )

        await app.db.execute(
            """
        UPDATE group_dm_channels
        SET icon = $1
        WHERE id = $2
        """,
            new_icon.icon_hash,
            channel_id,
        )

        await send_sys_message(channel_id, MessageType.CHANNEL_ICON_CHANGE, author_id)


@bp.route("/<int:channel_id>", methods=["PUT", "PATCH"])
async def update_channel(channel_id: int):
    """Update a channel's information"""
    user_id = await token_check()
    ctype, guild_id = await channel_check(user_id, channel_id)

    if ctype == ChannelType.DM:
        raise MissingPermissions()

    is_guild = ctype in GUILD_CHANS

    if is_guild:
        await channel_perm_check(user_id, channel_id, "manage_channels")

    j = validate(await request.get_json(), CHAN_UPDATE if is_guild else GROUP_DM_UPDATE)

    update_handler = {
        ChannelType.GUILD_TEXT: _update_text_channel,
        ChannelType.GUILD_VOICE: _update_voice_channel,
        ChannelType.GROUP_DM: _update_group_dm,
        ChannelType.GUILD_CATEGORY: None,
        ChannelType.GUILD_NEWS: _update_text_channel,
    }[ctype]

    if is_guild:
        await _update_channel_common(channel_id, guild_id, j)

    if update_handler:
        await update_handler(channel_id, j, user_id)

    chan = await app.storage.get_channel(channel_id, user_id=user_id)

    if is_guild:
        await app.dispatcher.guild.dispatch(guild_id, ("CHANNEL_UPDATE", chan))
    else:
        await app.dispatcher.channel.dispatch(channel_id, ("CHANNEL_UPDATE", chan))

    return jsonify(channel_view(chan))


@bp.route("/<int:channel_id>/typing", methods=["POST"])
async def trigger_typing(channel_id):
    user_id = await token_check()
    ctype, guild_id = await channel_check(user_id, channel_id)

    await app.dispatcher.channel.dispatch(
        channel_id,
        (
            "TYPING_START",
            {
                "channel_id": str(channel_id),
                "user_id": str(user_id),
                "timestamp": int(time.time()),
                "guild_id": str(guild_id) if ctype not in (ChannelType.DM, ChannelType.GROUP_DM) else None,
            },
        ),
    )

    return "", 204


@bp.route("/<int:channel_id>/followers", methods=["POST"])
async def _follow_channel(channel_id):
    """Follow a news channel"""
    user_id = await token_check()

    j = validate(await request.get_json(), FOLLOW_CHANNEL)
    destination_id = j["webhook_channel_id"]

    await channel_check(user_id, channel_id, only=ChannelType.GUILD_NEWS)
    await channel_check(user_id, destination_id, only=ChannelType.GUILD_TEXT)
    await channel_perm_check(user_id, channel_id, "read_messages")
    await channel_perm_check(user_id, destination_id, "manage_webhooks")

    channel = await app.storage.get_channel(channel_id)

    guild_id = await app.storage.guild_from_channel(channel_id)
    guild = await app.storage.get_guild(guild_id)

    guild_icon = await app.icons.generic_get("guild_icon", guild_id, guild["icon"])
    destination_id = j["webhook_channel_id"]
    destination_guild_id = await app.storage.guild_from_channel(destination_id)

    webhook_id = app.winter_factory.snowflake()
    token = secrets.token_urlsafe(40)
    webhook_icon = (hex(hash("user_avatar")).lstrip("-0x")[:3] + hex(hash(str(webhook_id))).lstrip("-0x")[:3] + "." + guild_icon.fs_hash)

    await app.db.execute(
        """
        INSERT INTO icons
            (scope, key, hash, mime)
        VALUES
            ('user_avatar', $1, $2, $3)
        """,
        str(webhook_id),
        webhook_icon,
        guild_icon.mime or "image/webp",
    )

    await app.db.execute(
        """
        INSERT INTO webhooks
            (id, type, guild_id, channel_id, creator_id, name, avatar, token, source_id)
        VALUES
            ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """,
        webhook_id,
        2,
        destination_guild_id,
        destination_id,
        user_id,
        f"{guild['name']} #{channel['name']}",
        webhook_icon,
        token,
        channel_id,
    )

    await _dispatch_webhook_update(destination_guild_id, destination_id)
    return jsonify({"channel_id": str(channel_id), "webhook_id": str(webhook_id)})


@bp.route("/<int:channel_id>/follower-stats", methods=["GET"])
async def _follower_stats(channel_id):  # Even the official API stubs this
    """Channel follower stats stub"""
    user_id = await token_check()
    await channel_check(user_id, channel_id, only=ChannelType.GUILD_NEWS)
    await channel_perm_check(user_id, channel_id, "read_messages")

    guild_id = await app.storage.guild_from_channel(channel_id)
    return jsonify({"guild_id": str(guild_id), "webhook_source_channel_id": None, "users_seen_ever": None})


@bp.route("/<int:channel_id>/messages/search", methods=["GET"])
async def _search_channel(channel_id):
    """Search in DMs or group DMs"""
    user_id = await token_check()
    await channel_check(user_id, channel_id)
    await channel_perm_check(user_id, channel_id, "read_messages")
    await channel_perm_check(user_id, channel_id, "read_history")

    return await handle_search(await app.storage.guild_from_channel(channel_id), channel_id)


@bp.route("/<int:channel_id>/application-commands/search", methods=["GET"])
async def _search_application_commands(channel_id):
    """Stub application command search"""
    return jsonify({"application_commands": [], "applications": [], "cursor": {"next": None, "previous": None, "repaired": None}})


# NOTE that those functions stay here until some other
# route or code wants it.


async def _msg_update_flags(message_id: int, flags: int):
    await app.db.execute(
        """
    UPDATE messages
    SET flags = $1
    WHERE id = $2
    """,
        flags,
        message_id,
    )


async def _msg_get_flags(message_id: int):
    return await app.db.fetchval(
        """
    SELECT flags
    FROM messages
    WHERE id = $1
    """,
        message_id,
    )


async def _msg_set_flags(message_id: int, new_flags: int):
    flags = await _msg_get_flags(message_id)
    flags |= new_flags
    await _msg_update_flags(message_id, flags)


async def _msg_unset_flags(message_id: int, unset_flags: int):
    flags = await _msg_get_flags(message_id)
    flags &= ~unset_flags
    await _msg_update_flags(message_id, flags)


@bp.route(
    "/<int:channel_id>/messages/<int:message_id>/suppress-embeds", methods=["POST"]
)
async def suppress_embeds(channel_id: int, message_id: int):
    """Toggle the embeds in a message.

    Either the author of the message or a channel member with the
    Manage Messages permission can run this route.
    """
    user_id = await token_check()
    await channel_check(user_id, channel_id)

    # the checks here have been copied from the delete_message()
    # handler on blueprints.channel.messages. maybe we can combine
    # them someday?
    author_id = await app.db.fetchval(
        """
    SELECT author_id FROM messages
    WHERE messages.id = $1
    """,
        message_id,
    )

    by_perms = await channel_perm_check(user_id, channel_id, "manage_messages", False)

    by_author = author_id == user_id

    can_suppress = by_perms or by_author
    if not can_suppress:
        raise MissingPermissions()

    j = validate(await request.get_json(), {"suppress": {"type": "boolean"}})

    suppress = j["suppress"]
    message = await app.storage.get_message(message_id)
    url_embeds = sum(1 for embed in message["embeds"] if embed["type"] == "url")

    # NOTE for any future self. discord doing flags an optional thing instead
    # of just giving 0 is a pretty bad idea because now i have to deal with
    # that behavior here, and likely in every other message update thing

    if suppress and url_embeds:
        # delete all embeds then dispatch an update
        await _msg_set_flags(message_id, MessageFlags.suppress_embeds)

        message["flags"] = message.get("flags", 0) | MessageFlags.suppress_embeds

        await msg_update_embeds(message, [])
    elif not suppress and not url_embeds:
        # spawn process_url_embed to restore the embeds, if any
        await _msg_unset_flags(message_id, MessageFlags.suppress_embeds)

        try:
            message.pop("flags")
        except KeyError:
            pass

        app.sched.spawn(process_url_embed(message))

    return "", 204


@bp.route(
    "/<int:channel_id>/messages/<int:message_id>/crosspost", methods=["POST"]
)
async def publish_message(channel_id: int, message_id: int):
    user_id = await token_check()
    await channel_check(user_id, channel_id, only=ChannelType.GUILD_NEWS)
    await channel_perm_check(user_id, channel_id, "send_messages")

    author_id = await app.db.fetchval(
        """
    SELECT author_id FROM messages
    WHERE messages.id = $1
    """,
        message_id,
    )

    if author_id != user_id:
        await channel_perm_check(user_id, channel_id, "manage_messages")

    hooks = await app.db.fetch(
        """
    SELECT name, avatar, id, token, channel_id, guild_id
    FROM webhooks
    WHERE source_id = $1
    """,
        channel_id,
    )
    hooks = [dict(hook) for hook in hooks]
    message = await app.storage.get_message(message_id, user_id)
    flags = message.get("flags", 0)

    if message["type"]:
        raise BadRequest(50068)

    # First we need to take care of the source message
    if flags & MessageFlags.crossposted == MessageFlags.crossposted:
        raise BadRequest(40033)

    await _msg_set_flags(message_id, MessageFlags.crossposted)
    message["flags"] = flags | MessageFlags.crossposted
    update_payload = {
        "id": str(message_id),
        "channel_id": str(channel_id),
        "guild_id": message["guild_id"],
        "flags": message["flags"],
    }
    await app.dispatcher.channel.dispatch(
        channel_id, ("MESSAGE_UPDATE", update_payload)
    )

    # Now we execute all these hooks
    content = message.get("content", "")
    for match in USER_MENTION.finditer(content):
        found_id = match.group(1)

        try:
            found_id = int(found_id)
        except ValueError:
            continue

        user = await app.storage.get_user(found_id)
        content = content.replace(match.group(0), user["username"] if user else "")

    result = {"content": content, "embeds": message.get("embeds", []), "sticker_ids": list(map(int, message.get("sticker_ids", []))), "flags": flags | MessageFlags.is_crosspost, "message_reference": {"guild_id": int(message["guild_id"]), "channel_id": channel_id, "message_id": message_id}}

    for hook in hooks:
        result_id = app.winter_factory.snowflake()

        async with app.db.acquire() as conn:
            await pg_set_json(conn)

            await conn.execute(
                """
                INSERT INTO messages (id, channel_id, guild_id,
                    content, message_type, embeds, flags, sticker_ids, message_reference)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
                result_id,
                hook["channel_id"],
                hook["guild_id"],
                result["content"],
                MessageType.DEFAULT.value,
                result["embeds"],
                result["flags"],
                result["sticker_ids"],
                result["message_reference"]
            )

            await conn.execute(
                """
            INSERT INTO message_webhook_info
                (message_id, webhook_id, name, avatar)
            VALUES
                ($1, $2, $3, $4)
            """,
                result_id,
                hook["id"],
                hook["name"],
                hook["avatar"],
            )

            payload = await app.storage.get_message(result_id, include_member=True)
            await app.dispatcher.channel.dispatch(hook["channel_id"], ("MESSAGE_CREATE", payload))
            app.sched.spawn(process_url_embed(payload))

    return jsonify(message_view(message))


@bp.route("/<int:channel_id>/messages/bulk_delete", methods=["POST"])
@bp.route("/<int:channel_id>/messages/bulk-delete", methods=["POST"])
async def bulk_delete(channel_id: int):
    user_id = await token_check()
    ctype, guild_id = await channel_check(user_id, channel_id)
    guild_id = guild_id if ctype in GUILD_CHANS else None

    await channel_perm_check(user_id, channel_id, "manage_messages")

    j = validate(await request.get_json(), BULK_DELETE)
    message_ids = set(j["messages"])

    if len(message_ids) > 100 or len(message_ids) < 2:
        raise BadRequest(50016)

    for message_id in message_ids:
        message_dt = app.winter_factory.to_datetime(message_id)
        delta = datetime.datetime.utcnow() - message_dt

        if delta.days > 14:
            raise BadRequest(50034)

    payload = {
        "guild_id": str(guild_id),
        "channel_id": str(channel_id),
        "ids": list(map(str, message_ids)),
    }

    # payload.guild_id is optional in the event, not nullable.
    if guild_id is None:
        payload.pop("guild_id")

    for id in message_ids:
        await _del_msg_fkeys(id, channel_id)

    await app.db.execute(
        """
    DELETE FROM messages
    WHERE
        channel_id = $1
        AND ARRAY[id] <@ $2::bigint[]
    """,
        channel_id,
        list(message_ids),
    )

    await app.dispatcher.channel.dispatch(channel_id, ("MESSAGE_DELETE_BULK", payload))
    return "", 204


@bp.route("/<int:channel_id>/voice-channel-effects", methods=["POST"])
async def voice_channel_effects(channel_id):
    user_id = await token_check()
    await channel_check(user_id, channel_id, only=ChannelType.GUILD_VOICE)
    await channel_perm_check(user_id, channel_id, "read_messages")
    await channel_perm_check(user_id, channel_id, "connect")

    j = validate(await request.get_json(), {"emoji_id": {"coerce": int, "nullable": True}, "emoji_name": {"coerce": str}})
    await app.dispatcher.channel.dispatch(channel_id, ("VOICE_CHANNEL_EFFECT_SEND", {"user_id": str(user_id), "channel_id": str(channel_id), "emoji": {"id": str(j["emoji_id"]) if j["emoji_id"] else None, "name": j["emoji_name"]}}))

    return "", 204
