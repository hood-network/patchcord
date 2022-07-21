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

from os.path import splitext

import aiohttp
from quart import Blueprint, current_app as app, send_file, redirect, make_response

from litecord.embed.sanitizer import make_md_req_url
from litecord.embed.schemas import EmbedURL

bp = Blueprint("images", __name__)


async def send_icon(scope, key, icon_hash, **kwargs):
    """Send an icon."""
    icon = await app.icons.generic_get(scope, key, icon_hash, **kwargs)

    if icon is None:
        return "", 404

    return await send_file(icon.as_path)


def splitext_(filepath):
    name, ext = splitext(filepath)
    return name, ext.strip(".")


@bp.route("/emojis/<emoji_file>", methods=["GET"])
async def _get_raw_emoji(emoji_file):
    emoji_id, ext = splitext_(emoji_file)
    return await send_icon("emoji", emoji_id, None, ext=ext)


@bp.route("/icons/<int:guild_id>/<icon_file>", methods=["GET"])
async def _get_guild_icon(guild_id: int, icon_file: str):
    icon_hash, ext = splitext_(icon_file)
    return await send_icon("guild_icon", guild_id, icon_hash, ext=ext)


@bp.route("/embed/avatars/<default_id>")
async def _get_default_user_avatar(default_id):
    # TODO: how do we determine which assets to use for this?
    # I don't think we can use discord assets (well we can for educational purposes)
    return redirect(f"https://cdn.discordapp.com/embed/avatars/{default_id}", code=301)


async def _handle_webhook_avatar(md_url_redir: str):
    md_url = make_md_req_url("img", EmbedURL(md_url_redir))
    return redirect(md_url)


@bp.route("/avatars/<int:user_id>/<avatar_file>")
async def _get_user_avatar(user_id, avatar_file):
    avatar_hash, ext = splitext_(avatar_file)

    # first, check if this is a webhook avatar to redir to
    md_url_redir = await app.db.fetchval(
        """
    SELECT md_url_redir
    FROM webhook_avatars
    WHERE webhook_id = $1 AND hash = $2
    """,
        user_id,
        avatar_hash,
    )

    if md_url_redir:
        return await _handle_webhook_avatar(md_url_redir)

    return await send_icon("user_avatar", user_id, avatar_hash, ext=ext)


@bp.route("/users/<int:user_id>/avatar-decorations/<avatar_file>")
@bp.route("/avatar-decorations/<int:user_id>/<avatar_file>")
async def _get_avatar_decoration(user_id, avatar_file):
    avatar_hash, ext = splitext_(avatar_file)
    return await send_icon("user_avatar_decoration", user_id, avatar_hash, ext=ext)


@bp.route("/guilds/<int:guild_id>/users/<int:user_id>/avatars/<avatar_file>")
async def _get_member_avatar(guild_id, user_id, avatar_file):
    avatar_hash, ext = splitext_(avatar_file)
    return await send_icon("member_avatar", f"{guild_id}_{user_id}", avatar_hash, ext=ext)


@bp.route("/guilds/<int:guild_id>/users/<int:user_id>/banners/<banner_file>")
async def _get_member_banner(guild_id, user_id, banner_file):
    avatar_hash, ext = splitext_(banner_file)
    return await send_icon("member_banner", f"{guild_id}_{user_id}", avatar_hash, ext=ext)


# @bp.route('/app-icons/<int:application_id>/<icon_hash>.<ext>')
# async def get_app_icon(application_id, icon_hash, ext):
#     pass


@bp.route("/channel-icons/<int:channel_id>/<icon_file>", methods=["GET"])
async def _get_gdm_icon(channel_id: int, icon_file: str):
    icon_hash, ext = splitext_(icon_file)
    return await send_icon("channel_icon", channel_id, icon_hash, ext=ext)


@bp.route("/splashes/<int:guild_id>/<icon_file>", methods=["GET"])
async def _get_guild_splash(guild_id: int, icon_file: str):
    icon_hash, ext = splitext_(icon_file)
    return await send_icon("guild_splash", guild_id, icon_hash, ext=ext)


@bp.route("/banners/<int:id>/<banner_file>", methods=["GET"])
async def _get_banner(id: int, banner_file: str):
    hash, ext = splitext_(banner_file)
    user = await app.storage.get_user(id)

    # This is used for guild and user banners
    if user:
        return await send_icon("user_banner", id, hash, ext=ext)
    return await send_icon("guild_banner", id, hash, ext=ext)


@bp.route("/channel-banners/<int:channel_id>/<banner_file>", methods=["GET"])
@bp.route("/channels/<int:channel_id>/banners/<banner_file>", methods=["GET"])
async def _get_channel_banner(channel_id: int, banner_file: str):
    banner_hash, ext = splitext_(banner_file)
    return await send_icon("channel_banner", channel_id, banner_hash, ext=ext)


@bp.route("/discovery-splashes/<int:guild_id>/<icon_file>", methods=["GET"])
async def _get_discovery_splash(guild_id: int, icon_file: str):
    icon_hash, ext = splitext_(icon_file)
    return await send_icon("guild_discovery_splash", guild_id, icon_hash, ext=ext)


@bp.route("/stickers/<sticker_id>", methods=["GET"])
@bp.route("/api/stickers/<sticker_id>", methods=["GET"])  # Client bug
async def sticker(sticker_id):
    """Proxy static sticker"""
    if sticker_id.endswith(".json"):
        url = f"https://discord.com/stickers/{sticker_id}"
    else:
        url = f"https://cdn.discordapp.com/stickers/{sticker_id}"

    async with aiohttp.request("GET", url) as resp:
        if not 300 > resp.status >= 200:
            return "Sticker not found", 404

        response = await make_response(await resp.read())
        response.status = resp.status
        response.headers["content-type"] = resp.headers["content-type"]
        if "etag" in resp.headers:
            response.headers["etag"] = resp.headers["etag"]