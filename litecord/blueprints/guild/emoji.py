from quart import Blueprint, jsonify, current_app as app

from litecord.auth import token_check
from litecord.blueprints.checks import guild_check

bp = Blueprint('guild.emoji', __name__)


@bp.route('/<int:guild_id>/emojis', methods=['GET'])
async def _get_guild_emoji(guild_id):
    user_id = await token_check()
    await guild_check(user_id, guild_id)
    return jsonify(
        await app.storage.get_guild_emojis(guild_id)
    )


@bp.route('/<int:guild_id>/emojis/<int:emoji_id>', methods=['GET'])
async def _get_guild_emoji_one(guild_id, emoji_id):
    user_id = await token_check()
    await guild_check(user_id, guild_id)
    return jsonify(
        await app.storage.get_emoji(emoji_id)
    )
