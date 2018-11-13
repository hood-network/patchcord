from enum import IntEnum

from quart import Blueprint, request, current_app as app, jsonify
from logbook import Logger


from litecord.utils import async_map
from litecord.blueprints.auth import token_check
from litecord.blueprints.checks import channel_check
from litecord.blueprints.channel.messages import (
    query_tuple_from_args, extract_limit
)

from litecord.enums import GUILD_CHANS


log = Logger(__name__)
bp = Blueprint('channel_reactions', __name__)

BASEPATH = '/<int:channel_id>/messages/<int:message_id>/reactions'


class EmojiType(IntEnum):
    CUSTOM = 0
    UNICODE = 1


def emoji_info_from_str(emoji: str) -> tuple:
    """Extract emoji information from an emoji string
    given on the reaction endpoints."""
    # custom emoji have an emoji of name:id
    # unicode emoji just have the raw unicode.

    # try checking if the emoji is custom or unicode
    emoji_type = 0 if ':' in emoji else 1
    emoji_type = EmojiType(emoji_type)

    # extract the emoji id OR the unicode value of the emoji
    # depending if it is custom or not
    emoji_id = (int(emoji.split(':')[1])
                if emoji_type == EmojiType.CUSTOM
                else emoji)

    emoji_name = emoji.split(':')[0]

    return emoji_type, emoji_id, emoji_name


def partial_emoji(emoji_type, emoji_id, emoji_name) -> dict:
    print(emoji_type, emoji_id, emoji_name)
    return {
        'id': None if emoji_type == EmojiType.UNICODE else emoji_id,
        'name': emoji_name if emoji_type == EmojiType.UNICODE else emoji_id
    }


def _make_payload(user_id, channel_id, message_id, partial):
    return {
        'user_id': str(user_id),
        'channel_id': str(channel_id),
        'message_id': str(message_id),
        'emoji': partial
    }


@bp.route(f'{BASEPATH}/<emoji>/@me', methods=['PUT'])
async def add_reaction(channel_id: int, message_id: int, emoji: str):
    """Put a reaction."""
    user_id = await token_check()

    # TODO: check READ_MESSAGE_HISTORY permission
    #       and ADD_REACTIONS. look on route docs.
    ctype, guild_id = await channel_check(user_id, channel_id)

    emoji_type, emoji_id, emoji_name = emoji_info_from_str(emoji)

    await app.db.execute(
        """
        INSERT INTO message_reactions (message_id, user_id,
            emoji_type, emoji_id, emoji_text)
        VALUES ($1, $2, $3, $4, $5)
        """, message_id, user_id, emoji_type,

        # if it is custom, we put the emoji_id on emoji_id
        # column, if it isn't, we put it on emoji_text
        # column.
        emoji_id if emoji_type == EmojiType.CUSTOM else None,
        emoji_id if emoji_type == EmojiType.UNICODE else None
    )

    partial = partial_emoji(emoji_type, emoji_id, emoji_name)
    payload = _make_payload(user_id, channel_id, message_id, partial)

    if ctype in GUILD_CHANS:
        payload['guild_id'] = str(guild_id)

    await app.dispatcher.dispatch(
        'channel', channel_id, 'MESSAGE_REACTION_ADD', payload)

    return '', 204


def emoji_sql(emoji_type, emoji_id, emoji_name, param=4):
    """Extract SQL clauses to search for specific emoji
    in the message_reactions table."""
    param = f'${param}'

    # know which column to filter with
    where_ext = (f'AND emoji_id = {param}'
                 if emoji_type == EmojiType.CUSTOM else
                 f'AND emoji_text = {param}')

    # which emoji to remove (custom or unicode)
    main_emoji = emoji_id if emoji_type == EmojiType.CUSTOM else emoji_name

    return where_ext, main_emoji


def _emoji_sql_simple(emoji: str, param=4):
    """Simpler version of _emoji_sql for functions that
    don't need the results from emoji_info_from_str."""
    emoji_type, emoji_id, emoji_name = emoji_info_from_str(emoji)
    return emoji_sql(emoji_type, emoji_id, emoji_name, param)


async def remove_reaction(channel_id: int, message_id: int,
                          user_id: int, emoji: str):
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
        """, message_id, user_id, emoji_type, main_emoji)

    partial = partial_emoji(emoji_type, emoji_id, emoji_name)
    payload = _make_payload(user_id, channel_id, message_id, partial)

    if ctype in GUILD_CHANS:
        payload['guild_id'] = str(guild_id)

    await app.dispatcher.dispatch(
        'channel', channel_id, 'MESSAGE_REACTION_REMOVE', payload)


@bp.route(f'{BASEPATH}/<emoji>/@me', methods=['DELETE'])
async def remove_own_reaction(channel_id, message_id, emoji):
    """Remove a reaction."""
    user_id = await token_check()

    await remove_reaction(channel_id, message_id, user_id, emoji)

    return '', 204


@bp.route(f'{BASEPATH}/<emoji>/<int:other_id>', methods=['DELETE'])
async def remove_user_reaction(channel_id, message_id, emoji, other_id):
    """Remove a reaction made by another user."""
    await token_check()

    # TODO: check MANAGE_MESSAGES permission (and use user_id
    # from token_check to do it)
    await remove_reaction(channel_id, message_id, other_id, emoji)

    return '', 204


@bp.route(f'{BASEPATH}/<emoji>', methods=['GET'])
async def list_users_reaction(channel_id, message_id, emoji):
    """Get the list of all users who reacted with a certain emoji."""
    user_id = await token_check()

    # this is not using either ctype or guild_id
    # that are returned by channel_check
    await channel_check(user_id, channel_id)

    limit = extract_limit(request, 25)
    before, after = query_tuple_from_args(request.args, limit)

    before_clause = 'AND user_id < $2' if before else ''
    after_clause = 'AND user_id > $3' if after else ''

    where_ext, main_emoji = _emoji_sql_simple(emoji, 4)

    rows = await app.db.fetch(f"""
    SELECT user_id
    FROM message_reactions
    WHERE message_id = $1 {before_clause} {after_clause} {where_ext}
    """, message_id, before, after, main_emoji)

    user_ids = [r['user_id'] for r in rows]
    users = await async_map(app.storage.get_user, user_ids)
    return jsonify(users)


@bp.route(f'{BASEPATH}', methods=['DELETE'])
async def remove_all_reactions(channel_id, message_id):
    """Remove all reactions in a message."""
    user_id = await token_check()

    # TODO: check MANAGE_MESSAGES permission
    ctype, guild_id = await channel_check(user_id, channel_id)

    await app.db.execute("""
    DELETE FROM message_reactions
    WHERE message_id = $1
    """, message_id)

    payload = {
        'channel_id': str(channel_id),
        'message_id': str(message_id),
    }

    if ctype in GUILD_CHANS:
        payload['guild_id'] = str(guild_id)

    await app.dispatcher.dispatch(
        'channel', channel_id, 'MESSAGE_REACTION_REMOVE_ALL', payload)
