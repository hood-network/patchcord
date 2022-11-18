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

from pathlib import Path
from typing import Optional, List, TYPE_CHECKING

from quart import Blueprint, request, jsonify
from logbook import Logger

from litecord.blueprints.auth import token_check
from litecord.blueprints.checks import channel_check, channel_perm_check
from litecord.errors import Forbidden, ManualFormError, MissingPermissions, NotFound
from litecord.enums import (
    MessageFlags,
    MessageType,
    ChannelType,
    GUILD_CHANS,
    PremiumType,
)

from litecord.schemas import (
    CHANNEL_GREET,
    validate,
    MESSAGE_CREATE,
    MESSAGE_UPDATE,
    ROLE_MENTION,
    USER_MENTION,
)
from litecord.utils import query_tuple_from_args, extract_limit, to_update, toggle_flag
from litecord.json import pg_set_json
from litecord.permissions import get_permissions

from litecord.embed.sanitizer import fill_embed
from litecord.embed.messages import process_url_embed
from litecord.common.channels import dm_pre_check, try_dm_state
from litecord.images import try_unlink
from litecord.common.messages import (
    PLAN_ID_TO_TYPE,
    msg_create_request,
    msg_create_check_content,
    msg_add_attachment,
    msg_guild_text_mentions,
)
from litecord.common.interop import message_view
from litecord.pubsub.user import dispatch_user
from litecord.typing_hax import app

if TYPE_CHECKING:
    from litecord.typing_hax import app, request
else:
    from quart import current_app as app, request

log = Logger(__name__)
bp = Blueprint("channel_messages", __name__)


async def message_search(
    channel_id: int,
    limit: int,
    before: Optional[int] = None,
    after: Optional[int] = None,
    order: str = "DESC",
) -> List[dict]:
    user_id = await token_check()

    where_clause = ""
    if before:
        where_clause += f"AND id < {before}"

    elif after:
        where_clause += f"AND id > {after}"

    return await app.storage.get_messages(
        user_id=user_id,
        where_clause=f"""
            WHERE channel_id = $1 {where_clause}
            ORDER BY id {order}
            LIMIT {limit}
        """,
        args=(channel_id,),
    )


async def around_message_search(
    channel_id: int,
    around_id: int,
    limit: int,
) -> List[dict]:
    # search limit/2 messages BEFORE around_id
    # search limit/2 messages AFTER around_id
    # merge it all together: before + [around_id] + after
    user_id = await token_check()
    halved_limit = limit // 2

    around_message = await app.storage.get_message(around_id, user_id)
    around_message = [around_message] if around_message else []
    before_messages = await message_search(
        channel_id, halved_limit, before=around_id, order="DESC"
    )
    after_messages = await message_search(
        channel_id, halved_limit, after=around_id, order="ASC"
    )
    return list(reversed(before_messages)) + around_message + after_messages


@bp.route("/<int:channel_id>/messages", methods=["GET"])
async def get_messages(channel_id):
    user_id = await token_check()

    await channel_check(user_id, channel_id)
    await channel_perm_check(user_id, channel_id, "read_history")
    return jsonify(await handle_get_messages(channel_id))


async def handle_get_messages(channel_id: int):
    limit = extract_limit(request, default=50)

    if "around" in request.args:
        messages = await around_message_search(
            channel_id, int(request.args["around"]), limit
        )
    else:
        before, after = query_tuple_from_args(request.args, limit)
        messages = await message_search(channel_id, limit, before=before, after=after)

    log.info("Fetched {} messages", len(messages))
    return [message_view(message) for message in messages]


@bp.route("/<int:channel_id>/messages/<int:message_id>", methods=["GET"])
async def get_single_message(channel_id, message_id):
    user_id = await token_check()
    await channel_check(user_id, channel_id)
    await channel_perm_check(user_id, channel_id, "read_history")

    message = await app.storage.get_message(message_id, user_id)
    if not message:
        raise NotFound(10008)

    return jsonify(message_view(message))


async def _dm_pre_dispatch(channel_id, peer_id):
    """Do some checks pre-MESSAGE_CREATE so we
    make sure the receiving party will handle everything."""

    # check the other party's dm_channel_state

    dm_state = await app.db.fetchval(
        """
    SELECT dm_id
    FROM dm_channel_state
    WHERE user_id = $1 AND dm_id = $2
    """,
        peer_id,
        channel_id,
    )

    if dm_state:
        # the peer already has the channel
        # opened, so we don't need to do anything
        return

    dm_chan = await app.storage.get_channel(channel_id)

    # dispatch CHANNEL_CREATE so the client knows which
    # channel the future event is about
    await dispatch_user(peer_id, ("CHANNEL_CREATE", dm_chan))

    # subscribe the peer to the channel
    await app.dispatcher.channel.sub(channel_id, peer_id)

    # insert it on dm_channel_state so the client
    # is subscribed on the future
    await try_dm_state(peer_id, channel_id)


async def create_message(
    channel_id: int,
    ctype: ChannelType,
    actual_guild_id: Optional[int],
    author_id: Optional[int],
    data: dict,
    *,
    recipient_id: Optional[int] = None,
    can_everyone: bool,
) -> int:
    message_id = app.winter_factory.snowflake()

    # We parse allowed_mentions
    allowed_mentions = await validate_allowed_mentions(data.get("allowed_mentions"))

    if (
        data["everyone_mention"]
        and allowed_mentions is not None
        and "everyone" not in allowed_mentions.get("parse", [])
    ):
        data["everyone_mention"] = False

    mentions = []
    mention_roles = []
    if data.get("content"):
        if (
            allowed_mentions is None
            or "users" in allowed_mentions.get("parse", [])
            or allowed_mentions.get("users")
        ):
            allowed = (allowed_mentions.get("users") or []) if allowed_mentions else []
            if ctype == ChannelType.GROUP_DM:
                members = await app.db.fetch(
                    """
                SELECT member_id
                FROM group_dm_members
                WHERE id = $1
                    """,
                    channel_id,
                )
                members = [member["member_id"] for member in members]
                allowed = [a for a in allowed if a in members] if allowed else members

            for match in USER_MENTION.finditer(data["content"]):
                found_id = match.group(1)
                try:
                    found_id = int(found_id)
                except ValueError:
                    continue

                if allowed and found_id not in allowed:
                    continue
                if ctype == ChannelType.DM and found_id not in (
                    author_id,
                    recipient_id,
                ):
                    continue
                if ctype not in (ChannelType.DM, ChannelType.GROUP_DM):
                    is_member = await app.db.fetchval(
                        """
                    SELECT user_id
                    FROM members
                    WHERE guild_id = $1 AND user_id = $2
                    """,
                        actual_guild_id,
                        found_id,
                    )
                    if not is_member:
                        continue

                mentions.append(found_id)

        if actual_guild_id and (
            allowed_mentions is None
            or "roles" in allowed_mentions.get("parse", [])
            or allowed_mentions.get("roles")
        ):
            guild_roles = await app.db.fetch(
                """
            SELECT id, mentionable
            FROM roles
            WHERE guild_id = $1
            """,
                actual_guild_id,
            )
            guild_roles = {role["id"]: role for role in guild_roles}
            allowed = (allowed_mentions.get("roles") or []) if allowed_mentions else []

            for match in ROLE_MENTION.finditer(data["content"]):
                found_id = match.group(1)
                try:
                    found_id = int(found_id)
                except ValueError:
                    continue

                if allowed and found_id not in allowed:
                    continue
                if found_id not in guild_roles:
                    continue
                if not guild_roles[found_id]["mentionable"] and not can_everyone:
                    continue

                mention_roles.append(found_id)

    if (
        data.get("message_reference")
        and not data.get("flags", 0) & MessageFlags.is_crosspost
        == MessageFlags.is_crosspost
        and (allowed_mentions is None or allowed_mentions.get("replied_user", False))
    ):
        reply_id = await app.db.fetchval(
            """
        SELECT author_id
        FROM messages
        WHERE id = $1
        """,
            int(data["message_reference"]["message_id"]),
        )
        if reply_id:
            mentions.append(reply_id)

    async with app.db.acquire() as conn:
        await pg_set_json(conn)

        await conn.execute(
            """
            INSERT INTO messages (id, channel_id, guild_id, author_id,
                content, tts, mention_everyone, nonce, message_type, flags,
                embeds, message_reference, sticker_ids, mentions, mention_roles)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
            """,
            message_id,
            channel_id,
            actual_guild_id,
            author_id,
            data["content"],
            data["tts"],
            data["everyone_mention"],
            data["nonce"],
            MessageType.DEFAULT.value
            if not data.get("message_reference")
            else MessageType.REPLY.value,
            data.get("flags") or 0,
            data.get("embeds") or [],
            data.get("message_reference") or None,
            data.get("sticker_ids") or [],
            mentions,
            mention_roles,
        )

    return message_id


async def _spawn_embed(payload, **kwargs):
    app.sched.spawn(process_url_embed(payload, **kwargs))


async def validate_allowed_mentions(allowed_mentions: Optional[dict]):
    if not allowed_mentions:
        return allowed_mentions

    for key in allowed_mentions.get("parse", []):
        if key == "everyone":
            continue
        if allowed_mentions.get(key):
            raise ManualFormError(
                allowed_mentions={
                    "code": "MESSAGE_ALLOWED_MENTIONS_PARSE_EXCLUSIVE",
                    "message": f'parse:["{key}"] and {key}: [ids...] are mutually exclusive.',
                }
            )


@bp.route("/<int:channel_id>/greet", methods=["POST"])
async def greet(channel_id):
    """Send a greet message."""
    user_id = await token_check()
    ctype, guild_id = await channel_check(user_id, channel_id)
    await channel_perm_check(user_id, channel_id, "read_messages")

    actual_guild_id: Optional[int] = None
    if ctype in GUILD_CHANS:
        await channel_perm_check(user_id, channel_id, "send_messages")
        actual_guild_id = guild_id

    j = validate(await request.get_json(), CHANNEL_GREET)
    message_id = await create_message(
        channel_id,
        ctype,
        actual_guild_id,
        user_id,
        {
            "content": "",
            "tts": False,
            "nonce": None,
            "everyone_mention": False,
            "embeds": [],
            "message_reference": j.get("message_reference"),
            "allowed_mentions": None,
            "sticker_ids": j["sticker_ids"],
            "flags": 0,
        },
        can_everyone=False,
    )

    payload = await app.storage.get_message(message_id, user_id, include_member=True)

    if ctype == ChannelType.DM:
        # guild id here is the peer's ID.
        await _dm_pre_dispatch(channel_id, user_id)
        await _dm_pre_dispatch(channel_id, guild_id)

    await app.dispatcher.channel.dispatch(channel_id, ("MESSAGE_CREATE", payload))

    # update read state for the author
    await app.db.execute(
        """
    UPDATE user_read_state
    SET last_message_id = $1
    WHERE channel_id = $2 AND user_id = $3
    """,
        message_id,
        channel_id,
        user_id,
    )

    if ctype not in (ChannelType.DM, ChannelType.GROUP_DM):
        await msg_guild_text_mentions(payload, guild_id, False, False)

    return jsonify(message_view(payload))


@bp.route("/<int:channel_id>/messages", methods=["POST"])
async def _create_message(channel_id):
    """Create a message."""
    user_id = await token_check()
    ctype, guild_id = await channel_check(user_id, channel_id)
    await channel_perm_check(user_id, channel_id, "read_messages")

    actual_guild_id: Optional[int] = None

    if ctype in GUILD_CHANS:
        await channel_perm_check(user_id, channel_id, "send_messages")
        actual_guild_id = guild_id

    payload_json, files = await msg_create_request()
    j = validate(payload_json, MESSAGE_CREATE)

    if len(j["content"]) > 2000:
        plan_id = await app.db.fetchval(
            """
        SELECT payment_gateway_plan_id
        FROM user_subscriptions
        WHERE status = 1
            AND user_id = $1
        """,
            user_id,
        )
        premium_type = PLAN_ID_TO_TYPE.get(plan_id)
        if premium_type != PremiumType.TIER_2:
            raise ManualFormError(
                content={
                    "code": "BASE_TYPE_MAX_LENGTH",
                    "message": "Must be 2000 or fewer in length.",
                }
            )

    msg_create_check_content(payload_json, files)

    if ctype == ChannelType.DM:
        # guild_id is the dm's peer_id
        await dm_pre_check(user_id, channel_id, guild_id)

    can_everyone = (
        await channel_perm_check(user_id, channel_id, "mention_everyone", False)
        and ctype != ChannelType.DM
    )

    mentions_everyone = ("@everyone" in j["content"]) and can_everyone
    mentions_here = ("@here" in j["content"]) and can_everyone

    is_tts = j.get("tts", False) and await channel_perm_check(
        user_id, channel_id, "send_tts_messages", False
    )

    embeds = [
        await fill_embed(embed)
        for embed in (
            (j.get("embeds") or []) or [j["embed"]]
            if "embed" in j and j["embed"]
            else []
        )
    ]
    message_id = await create_message(
        channel_id,
        ctype,
        actual_guild_id,
        user_id,
        {
            "content": j["content"] or "",
            "tts": is_tts,
            "nonce": j.get("nonce"),
            "everyone_mention": mentions_everyone or mentions_here,
            # fill_embed takes care of filling proxy and width/height
            "embeds": embeds,
            "message_reference": j.get("message_reference"),
            "allowed_mentions": j.get("allowed_mentions"),
            "sticker_ids": j.get("sticker_ids"),
            "flags": MessageFlags.suppress_embeds
            if (
                j.get("flags", 0) & MessageFlags.suppress_embeds
                == MessageFlags.suppress_embeds
            )
            else 0,
        },
        recipient_id=guild_id if ctype == ChannelType.DM else None,
        can_everyone=can_everyone,
    )

    # for each file given, we add it as an attachment
    for pre_attachment in files:
        await msg_add_attachment(message_id, channel_id, user_id, pre_attachment)

    payload = await app.storage.get_message(message_id, user_id, include_member=True)

    if ctype == ChannelType.DM:
        # guild id here is the peer's ID.
        await _dm_pre_dispatch(channel_id, user_id)
        await _dm_pre_dispatch(channel_id, guild_id)

    await app.dispatcher.channel.dispatch(channel_id, ("MESSAGE_CREATE", payload))

    # spawn url processor for embedding of images
    perms = await get_permissions(user_id, channel_id)
    if perms.bits.embed_links:
        await _spawn_embed(payload)

    # update read state for the author
    await app.db.execute(
        """
    UPDATE user_read_state
    SET last_message_id = $1
    WHERE channel_id = $2 AND user_id = $3
    """,
        message_id,
        channel_id,
        user_id,
    )

    if ctype not in (ChannelType.DM, ChannelType.GROUP_DM):
        await msg_guild_text_mentions(
            payload, guild_id, mentions_everyone, mentions_here
        )

    return jsonify(message_view(payload))


@bp.route("/<int:channel_id>/messages/<int:message_id>", methods=["PATCH"])
async def edit_message(channel_id, message_id):
    user_id = await token_check()
    await channel_check(user_id, channel_id)

    author_id = await app.db.fetchval(
        """
    SELECT author_id FROM messages
    WHERE messages.id = $1
    """,
        message_id,
    )

    if not author_id == user_id:
        raise Forbidden(50005)

    j = validate(await request.get_json(), MESSAGE_UPDATE)
    updated = False
    old_message = await app.storage.get_message(message_id)
    embeds = None

    if to_update(j, old_message, "allowed_mentions"):
        updated = True
        # TODO

    flags = None
    if "flags" in j:
        old_flags = MessageFlags.from_int(old_message.get("flags", 0))
        new_flags = MessageFlags.from_int(int(j["flags"]))

        toggle_flag(
            old_flags, MessageFlags.suppress_embeds, new_flags.is_suppress_embeds
        )

        if old_flags.value != old_message["flags"]:
            await app.db.execute(
                """
            UPDATE messages
            SET flags = $1
            WHERE id = $2
            """,
                old_flags.value,
                message_id,
            )
            flags = old_flags.value

    if to_update(j, old_message, "content"):
        updated = True
        await app.db.execute(
            """
        UPDATE messages
        SET content=$1
        WHERE messages.id = $2
        """,
            j["content"] or "",
            message_id,
        )

    if "embed" in j or "embeds" in j:
        updated = True
        embeds = [
            await fill_embed(embed)
            for embed in (
                (j.get("embeds") or []) or [j["embed"]]
                if "embed" in j and j["embed"]
                else []
            )
        ]
        await app.db.execute(
            """
        UPDATE messages
        SET embeds=$1
        WHERE messages.id = $2
        """,
            embeds,
            message_id,
        )

        # the artificial delay keeps consistency between the events, since
        # it makes more sense for the MESSAGE_UPDATE with new content to come
        # BEFORE the MESSAGE_UPDATE with the new embeds (based on content)
        perms = await get_permissions(user_id, channel_id)
        if perms.bits.embed_links:
            await _spawn_embed(
                {
                    "id": message_id,
                    "channel_id": channel_id,
                    "content": j["content"],
                    "embeds": old_message["embeds"],
                    "flags": flags
                    if flags is not None
                    else old_message.get("flags", 0),
                },
                delay=0.2,
            )

    # only set new timestamp upon actual update
    if updated:
        await app.db.execute(
            """
        UPDATE messages
        SET edited_at = (now() at time zone 'utc')
        WHERE id = $1
        """,
            message_id,
        )

    message = await app.storage.get_message(message_id, user_id)

    # only dispatch MESSAGE_UPDATE if any update
    # actually happened
    if updated:
        await app.dispatcher.channel.dispatch(channel_id, ("MESSAGE_UPDATE", message))

    # now we handle crossposted messages
    if updated and (
        message.get("flags", 0) & MessageFlags.crossposted == MessageFlags.crossposted
    ):
        async with app.db.acquire() as conn:
            await pg_set_json(conn)

            guild_id = await app.storage.guild_from_channel(channel_id)
            message_reference = {
                "guild_id": guild_id,
                "channel_id": channel_id,
                "message_id": message_id,
            }

            ids = await conn.fetch(
                """
            SELECT id, channel_id, flags
            FROM messages
            WHERE author_id = NULL AND message_reference = $1
            """,
                message_reference,
            )
            for row in ids:
                id = row["id"]

                # we must make sure we only update and refurl embeds if an update actually occurred
                refurl = False
                query = """
                UPDATE messages
                SET content=$2, flags=$3, {}edited_at=(now() at time zone 'utc')
                WHERE messages.id = $1
                """
                args = [id, message["content"], message["flags"]]
                if embeds is not None or to_update(j, old_message, "content"):
                    refurl = True
                    query = query.format("embeds=$4, ")
                    args.append(embeds)

                await conn.execute(query.format(""), *args)

                if refurl:
                    await _spawn_embed(
                        {
                            "id": id,
                            "channel_id": row["channel_id"],
                            "content": j["content"],
                            "embeds": embeds
                            if embeds is not None
                            else old_message["embeds"],
                        },
                        delay=0.2,
                    )

                message = await app.storage.get_message(id)
                await app.dispatcher.channel.dispatch(
                    row["channel_id"], ("MESSAGE_UPDATE", message)
                )

    return jsonify(message_view(message))


async def _del_msg_fkeys(message_id: int, channel_id: int):
    guild_id = await app.storage.guild_from_channel(channel_id)

    attachs = await app.db.fetch(
        """
    SELECT id FROM attachments
    WHERE message_id = $1
    """,
        message_id,
    )

    attachs = [r["id"] for r in attachs]

    attachments = Path("./attachments")
    for attach_id in attachs:
        # anything starting with the given attachment shall be
        # deleted, because there may be resizes of the original
        # attachment laying around.
        for filepath in attachments.glob(f"{attach_id}*"):
            try_unlink(filepath)

    # after trying to delete all available attachments, delete
    # them from the database.

    # handle crossposted messages >.<
    async with app.db.acquire() as conn:
        await pg_set_json(conn)

        message_reference = {
            "guild_id": guild_id,
            "channel_id": channel_id,
            "message_id": message_id,
        }

        ids = await conn.fetch(
            """
        SELECT id, flags
        FROM messages
        WHERE author_id = NULL AND message_reference = $1
        """,
            message_reference,
        )
        for row in ids:
            id = row["id"]
            await conn.execute(
                """
            UPDATE messages
            SET content='[Original Message Deleted]', embeds='[]', edited_at=(now() at time zone 'utc'), sticker_ids='[]', flags=$2
            WHERE messages.id = $1
            """,
                id,
                row["flags"] | MessageFlags.source_message_deleted,
            )

            message = await app.storage.get_message(id)
            await app.dispatcher.channel.dispatch(
                channel_id, ("MESSAGE_UPDATE", message)
            )

    # take the chance and delete all the data from the other tables too!

    tables = [
        "attachments",
        "message_webhook_info",
        "message_reactions",
        "channel_pins",
    ]

    for table in tables:
        await app.db.execute(
            f"""
        DELETE FROM {table}
        WHERE message_id = $1
        """,
            message_id,
        )


@bp.route("/<int:channel_id>/messages/<int:message_id>", methods=["DELETE"])
async def delete_message(channel_id, message_id):
    user_id = await token_check()
    _ctype, guild_id = await channel_check(user_id, channel_id)

    author_id = await app.db.fetchval(
        """
    SELECT author_id FROM messages
    WHERE messages.id = $1
    """,
        message_id,
    )

    by_perm = await channel_perm_check(user_id, channel_id, "manage_messages", False)

    by_ownership = author_id == user_id

    can_delete = by_perm or by_ownership
    if not can_delete:
        raise MissingPermissions()

    await _del_msg_fkeys(message_id, channel_id)

    await app.db.execute(
        """
    DELETE FROM messages
    WHERE messages.id = $1
    """,
        message_id,
    )

    await app.dispatcher.channel.dispatch(
        channel_id,
        (
            "MESSAGE_DELETE",
            {
                "id": str(message_id),
                "channel_id": str(channel_id),
                # for lazy guilds
                "guild_id": str(guild_id),
            },
        ),
    )

    return "", 204
