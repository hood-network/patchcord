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

from quart import Blueprint, jsonify
from typing import TYPE_CHECKING

from litecord.auth import token_check
from litecord.blueprints.checks import guild_check, guild_perm_check
from litecord.schemas import validate, NEW_EMOJI, PATCH_EMOJI

from litecord.types import KILOBYTES
from litecord.images import parse_data_uri
from litecord.errors import BadRequest, ManualFormError, NotFound

if TYPE_CHECKING:
    from litecord.typing_hax import app, request
else:
    from quart import current_app as app, request

bp = Blueprint("guild_emoji", __name__)


async def _dispatch_emojis(guild_id):
    """Dispatch a Guild Emojis Update payload to a guild."""
    await app.dispatcher.guild.dispatch(
        guild_id,
        (
            "GUILD_EMOJIS_UPDATE",
            {
                "guild_id": str(guild_id),
                "emojis": await app.storage.get_guild_emojis(guild_id),
            },
        ),
    )


@bp.route("/<int:guild_id>/emojis", methods=["GET"])
async def _get_guild_emoji(guild_id):
    user_id = await token_check()
    await guild_check(user_id, guild_id)
    return jsonify(await app.storage.get_guild_emojis(guild_id))


@bp.route("/<int:guild_id>/emojis/<int:emoji_id>", methods=["GET"])
async def _get_guild_emoji_one(guild_id, emoji_id):
    user_id = await token_check()
    await guild_check(user_id, guild_id)
    return jsonify(await app.storage.get_emoji(emoji_id))


async def _guild_emoji_size_check(guild_id: int, mime: str):
    limit = 50
    if await app.storage.has_feature(guild_id, "MORE_EMOJI"):
        limit = 200

    # NOTE: I'm assuming you can have 200 animated emojis.
    select_animated = mime == "image/gif"

    total_emoji = await app.db.fetchval(
        """
    SELECT COUNT(*) FROM guild_emoji
    WHERE guild_id = $1 AND animated = $2
    """,
        guild_id,
        select_animated,
    )

    if total_emoji >= limit:
        # TODO: really return a BadRequest? needs more looking.
        raise BadRequest(30008, limit)


@bp.route("/<int:guild_id>/emojis", methods=["POST"])
async def _put_emoji(guild_id):
    user_id = await token_check()

    await guild_check(user_id, guild_id)
    await guild_perm_check(user_id, guild_id, "manage_emojis")

    j = validate(await request.get_json(), NEW_EMOJI)

    # we have to parse it before passing on so that we know which
    # size to check.
    mime, _ = parse_data_uri(j["image"])
    await _guild_emoji_size_check(guild_id, mime)

    emoji_id = app.winter_factory.snowflake()

    icon = await app.icons.put(
        "emoji",
        emoji_id,
        j["image"],
        # limits to emojis
        bsize=128 * KILOBYTES,
        size=(128, 128),
    )

    if icon is None:
        raise ManualFormError(
            image={"code": "IMAGE_INVALID", "message": "Invalid image data"}
        )

    # TODO: better way to detect animated emoji rather than just gifs,
    # maybe a list perhaps?
    await app.db.execute(
        """
        INSERT INTO guild_emoji
            (id, guild_id, uploader_id, name, image, animated)
        VALUES
            ($1, $2, $3, $4, $5, $6)
        """,
        emoji_id,
        guild_id,
        user_id,
        j["name"],
        icon.icon_hash,
        icon.mime == "image/gif",
    )

    await _dispatch_emojis(guild_id)

    return jsonify(await app.storage.get_emoji(emoji_id))


@bp.route("/<int:guild_id>/emojis/<int:emoji_id>", methods=["PATCH"])
async def _patch_emoji(guild_id, emoji_id):
    user_id = await token_check()

    await guild_check(user_id, guild_id)
    await guild_perm_check(user_id, guild_id, "manage_emojis")

    j = validate(await request.get_json(), PATCH_EMOJI)
    emoji = await app.storage.get_emoji(emoji_id)

    # if emoji.name is still the same, we don't update anything
    # or send ane events, just return the same emoji we'd send
    # as if we updated it.
    if j["name"] == emoji["name"]:
        return jsonify(emoji)

    await app.db.execute(
        """
    UPDATE guild_emoji
    SET name = $1
    WHERE id = $2
    """,
        j["name"],
        emoji_id,
    )

    await _dispatch_emojis(guild_id)

    return jsonify(await app.storage.get_emoji(emoji_id))


@bp.route("/<int:guild_id>/emojis/<int:emoji_id>", methods=["DELETE"])
async def _del_emoji(guild_id, emoji_id):
    user_id = await token_check()

    await guild_check(user_id, guild_id)
    await guild_perm_check(user_id, guild_id, "manage_emojis")

    res = await app.db.execute(
        """
    DELETE FROM guild_emoji
    WHERE id = $1
    """,
        emoji_id,
    )
    if res == "DELETE 0":
        raise NotFound(10014)

    await _dispatch_emojis(guild_id)
    return "", 204
