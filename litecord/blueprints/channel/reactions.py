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

from enum import IntEnum
from typing import List, Union, Tuple, TypedDict, Optional, TYPE_CHECKING

from quart import Blueprint, request, jsonify
from logbook import Logger
from emoji import EMOJI_DATA

from litecord.errors import BadRequest
from litecord.utils import async_map, query_tuple_from_args, extract_limit
from litecord.blueprints.auth import token_check
from litecord.blueprints.checks import channel_check, channel_perm_check
from litecord.common.messages import PLAN_ID_TO_TYPE

from litecord.enums import GUILD_CHANS
from litecord.enums import PremiumType

if TYPE_CHECKING:
    from litecord.typing_hax import app, request
else:
    from quart import current_app as app, request

log = Logger(__name__)
bp = Blueprint("channel_reactions", __name__)

BASEPATH = "/<int:channel_id>/messages/<int:message_id>/reactions"


class EmojiType(IntEnum):
    CUSTOM = 0
    UNICODE = 1


def emoji_info_from_str(emoji: str) -> tuple:
    """Extract emoji information from an emoji string
    given on the reaction endpoints."""
    # custom emoji have an emoji of name:id
    # unicode emoji just have the raw unicode.

    # try checking if the emoji is custom or unicode
    emoji_type = EmojiType(0 if ":" in emoji else 1)

    # extract the emoji id OR the unicode value of the emoji
    # depending if it is custom or not
    emoji_id = int(emoji.split(":")[1]) if emoji_type == EmojiType.CUSTOM else emoji

    emoji_name = emoji.split(":")[0]

    return emoji_type, emoji_id, emoji_name


class PartialEmoji(TypedDict):
    id: Optional[Union[str, int]]
    name: str


def partial_emoji(emoji_type, emoji_id, emoji_name) -> PartialEmoji:
    print(emoji_type, emoji_id, emoji_name)
    return {
        "id": None if emoji_type == EmojiType.UNICODE else str(emoji_id),
        "name": emoji_name or str(emoji_id),
    }


def _make_payload(user_id, channel_id, message_id, partial):
    return {
        "user_id": str(user_id),
        "channel_id": str(channel_id),
        "message_id": str(message_id),
        "emoji": partial,
    }


@bp.route(f"{BASEPATH}/<emoji>/@me", methods=["PUT"])
async def add_reaction(channel_id: int, message_id: int, emoji: str):
    """Put a reaction."""
    user_id = await token_check()

    ctype, guild_id = await channel_check(user_id, channel_id)
    await channel_perm_check(user_id, channel_id, "read_history")

    emoji_type, upstream_emoji_id, emoji_name = emoji_info_from_str(emoji)

    emoji_id = upstream_emoji_id if emoji_type == EmojiType.CUSTOM else None
    emoji_text = upstream_emoji_id if emoji_type == EmojiType.UNICODE else None

    # either one must exist
    assert emoji_id or emoji_text

    # ADD_REACTIONS is only checked when this is the first
    # reaction in a message.
    reaction_count = await app.db.fetchval(
        """
        SELECT COUNT(*)
        FROM message_reactions
        WHERE message_id = $1
        AND emoji_type = $2
        AND emoji_id = $3
        AND emoji_text = $4
        """,
        message_id,
        emoji_type,
        emoji_id,
        emoji_text,
    )

    if reaction_count == 0:
        await channel_perm_check(user_id, channel_id, "add_reactions")

        # First reaction, so nitro check
        if emoji_type == EmojiType.CUSTOM:
            row = await app.db.fetchrow(
                """
                 SELECT animated,
                        guild_id,
                        (SELECT payment_gateway_plan_id
                         FROM   user_subscriptions
                         WHERE  status = 1
                         AND user_id = $2) AS plan_id
                FROM   guild_emoji
                WHERE  id = $1; 
                """,
                emoji_id,
                user_id,
            )

            # If the emoji does not exist
            if not row:
                raise BadRequest(10014)

            premium_type = PLAN_ID_TO_TYPE.get(row["plan_id"])
            if (row["animated"] or (row["guild_id"] != guild_id)) and not premium_type:
                raise BadRequest(10014)

    await app.db.execute(
        """
        INSERT INTO message_reactions
            (message_id, user_id, emoji_type, emoji_id, emoji_text)
        VALUES
            ($1, $2, $3, $4, $5)
        """,
        message_id,
        user_id,
        emoji_type,
        # if it is custom, we put the emoji_id on emoji_id
        # column, if it isn't, we put it on emoji_text
        # column.
        emoji_id,
        emoji_text,
    )

    partial = partial_emoji(emoji_type, emoji_id, emoji_name)
    payload = _make_payload(user_id, channel_id, message_id, partial)

    if ctype in GUILD_CHANS:
        payload["guild_id"] = str(guild_id)

    await app.dispatcher.channel.dispatch(channel_id, ("MESSAGE_REACTION_ADD", payload))
    return "", 204


def emoji_sql(
    emoji_type, emoji_id, emoji_name, param_index: int = 4
) -> Tuple[str, Union[int, str]]:
    """Extract SQL clauses to search for specific emoji in the message_reactions table."""
    param = f"${param_index}"

    assert emoji_type in (EmojiType.CUSTOM, EmojiType.UNICODE)

    if emoji_type == EmojiType.CUSTOM:
        where_ext = f"AND emoji_id = {param}"
        main_emoji = emoji_id
    elif emoji_type == EmojiType.UNICODE:
        # fun fact, emojis are length 1 in python? i'll use this to the
        # best of my ability, lol
        if len(emoji_name) != 1 or emoji_name not in EMOJI_DATA:
            raise BadRequest(10014)

        where_ext = f"AND emoji_text = {param}"
        main_emoji = emoji_name

    return where_ext, main_emoji


def _emoji_sql_simple(emoji: str, param=4):
    """Simpler version of _emoji_sql for functions that
    don't need the results from emoji_info_from_str."""
    emoji_type, emoji_id, emoji_name = emoji_info_from_str(emoji)
    return emoji_sql(emoji_type, emoji_id, emoji_name, param)


async def _remove_reaction(channel_id: int, message_id: int, user_id: int, emoji: str):
    """Remove given reaction from a message."""
    ctype, guild_id = await channel_check(user_id, channel_id)

    emoji_type, emoji_id, emoji_name = emoji_info_from_str(emoji)
    where_ext, main_emoji = emoji_sql(emoji_type, emoji_id, emoji_name)

    await app.db.execute(
        f"""
        DELETE FROM message_reactions
        WHERE message_id = $1
          AND user_id = $2
          AND emoji_type = $3
          {where_ext}
        """,
        message_id,
        user_id,
        emoji_type,
        main_emoji,
    )

    partial = partial_emoji(emoji_type, emoji_id, emoji_name)
    payload = _make_payload(user_id, channel_id, message_id, partial)

    if ctype in GUILD_CHANS:
        payload["guild_id"] = str(guild_id)

    await app.dispatcher.channel.dispatch(
        channel_id, ("MESSAGE_REACTION_REMOVE", payload)
    )


@bp.route(f"{BASEPATH}/<emoji>/@me", methods=["DELETE"])
async def remove_own_reaction(channel_id, message_id, emoji):
    """Remove a reaction."""
    user_id = await token_check()

    await _remove_reaction(channel_id, message_id, user_id, emoji)
    return "", 204


@bp.route(f"{BASEPATH}/<emoji>/<int:other_id>", methods=["DELETE"])
async def remove_user_reaction(channel_id, message_id, emoji, other_id):
    """Remove a reaction made by another user."""
    user_id = await token_check()
    await channel_perm_check(user_id, channel_id, "manage_messages")

    await _remove_reaction(channel_id, message_id, other_id, emoji)
    return "", 204


@bp.route(f"{BASEPATH}/<emoji>", methods=["GET"])
async def list_users_reaction(channel_id, message_id, emoji):
    """Get the list of all users who reacted with a certain emoji."""
    user_id = await token_check()

    # this is not using either ctype or guild_id
    # that are returned by channel_check
    await channel_check(user_id, channel_id)

    limit = extract_limit(request, default=25)
    before, after = query_tuple_from_args(request.args, limit)

    args: List[Union[int, str]] = [message_id]

    before_clause = "AND user_id < $2" if before else ""
    if before_clause:
        args.append(before)

    after_clause = f"AND user_id > ${len(args) + 1}" if after else ""
    if after_clause:
        args.append(after)

    where_ext, main_emoji = _emoji_sql_simple(emoji, len(args) + 1)
    args.append(main_emoji)

    rows = await app.db.fetch(
        f"""
        SELECT user_id
        FROM message_reactions
        WHERE message_id = $1 {before_clause} {after_clause} {where_ext}
        """,
        *args,
    )

    user_ids = [r["user_id"] for r in rows]
    users = await async_map(app.storage.get_user, user_ids)
    return jsonify(users)


@bp.route(f"{BASEPATH}", methods=["DELETE"])
async def remove_all_reactions(channel_id, message_id):
    """Remove all reactions in a message."""
    user_id = await token_check()

    ctype, guild_id = await channel_check(user_id, channel_id)
    await channel_perm_check(user_id, channel_id, "manage_messages")

    await app.db.execute(
        """
    DELETE FROM message_reactions
    WHERE message_id = $1
    """,
        message_id,
    )

    payload = {"channel_id": str(channel_id), "message_id": str(message_id)}

    if ctype in GUILD_CHANS:
        payload["guild_id"] = str(guild_id)

    await app.dispatcher.channel.dispatch(
        channel_id, ("MESSAGE_REACTION_REMOVE_ALL", payload)
    )
