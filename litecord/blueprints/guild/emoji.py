"""

Litecord
Copyright (C) 2018  Luna Mendes

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

from quart import Blueprint, jsonify, current_app as app, request

from litecord.auth import token_check
from litecord.blueprints.checks import guild_check, guild_perm_check
from litecord.schemas import validate, NEW_EMOJI, PATCH_EMOJI
from litecord.snowflake import get_snowflake
from litecord.types import KILOBYTES

bp = Blueprint('guild.emoji', __name__)


async def _dispatch_emojis(guild_id):
    """Dispatch a Guild Emojis Update payload to a guild."""
    await app.dispatcher.dispatch('guild', guild_id, 'GUILD_EMOJIS_UPDATE', {
        'guild_id': str(guild_id),
        'emojis': await app.storage.get_guild_emojis(guild_id)
    })


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


@bp.route('/<int:guild_id>/emojis', methods=['POST'])
async def _put_emoji(guild_id):
    user_id = await token_check()

    await guild_check(user_id, guild_id)
    await guild_perm_check(user_id, guild_id, 'manage_emojis')

    j = validate(await request.get_json(), NEW_EMOJI)

    emoji_id = get_snowflake()

    icon = await app.icons.put(
        'emoji', emoji_id, j['image'],

        # limits to emojis
        bsize=128 * KILOBYTES, size=(128, 128)
    )

    if not icon:
        return '', 400

    await app.db.execute(
        """
        INSERT INTO guild_emoji
            (id, guild_id, uploader_id, name, image, animated)
        VALUES
            ($1, $2, $3, $4, $5, $6)
        """,
        emoji_id, guild_id, user_id,
        j['name'],
        icon.icon_hash,
        icon.mime == 'image/gif')

    await _dispatch_emojis(guild_id)

    return jsonify(
        await app.storage.get_emoji(emoji_id)
    )


@bp.route('/<int:guild_id>/emojis/<int:emoji_id>', methods=['PATCH'])
async def _patch_emoji(guild_id, emoji_id):
    user_id = await token_check()

    await guild_check(user_id, guild_id)
    await guild_perm_check(user_id, guild_id, 'manage_emojis')

    j = validate(await request.get_json(), PATCH_EMOJI)

    # TODO: check if it actually updated anything
    await app.db.execute("""
    UPDATE guild_emoji
    SET name = $1
    WHERE id = $2
    """, j['name'], emoji_id)

    await _dispatch_emojis(guild_id)

    return jsonify(
        await app.storage.get_emoji(emoji_id)
    )


@bp.route('/<int:guild_id>/emojis/<int:emoji_id>', methods=['DELETE'])
async def _del_emoji(guild_id, emoji_id):
    user_id = await token_check()

    await guild_check(user_id, guild_id)
    await guild_perm_check(user_id, guild_id, 'manage_emojis')

    # TODO: check if actually deleted
    await app.db.execute("""
    DELETE FROM guild_emoji
    WHERE id = $2
    """, emoji_id)

    await _dispatch_emojis(guild_id)
    return '', 204
