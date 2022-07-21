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

import aiohttp
from quart import Blueprint, redirect, request, make_response

bp = Blueprint("stickers", __name__)


@bp.route("/sticker-packs", methods=["GET"])
@bp.route("/users/@me/sticker-packs", methods=["GET"])
async def sticker_packs():
    """Send static sticker packs"""
    return redirect(f"https://discord.com/api/v9/sticker-packs?{request.query_string.decode()}", code=308)


@bp.route("/sticker-packs/<sticker_pack>", methods=["GET"])
async def sticker_pack(sticker_pack):
    """Send static sticker pack"""
    return redirect(f"https://discord.com/api/v9/sticker-packs/{sticker_pack}?{request.query_string.decode()}", code=308)


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


@bp.route("/gifs/select", methods=["POST"])
async def stub_select():
    """Stub for select telemetry"""
    return "", 204


@bp.route("/gifs/<path:path>", methods=["GET", "POST"])
async def gifs(path):
    """Send gifs and stuff"""
    return redirect(f"https://discord.com/api/v9/gifs/{path}?{request.query_string.decode()}", code=308)


@bp.route("/integrations/<provider>/search", methods=["GET"])
async def search_gifs(provider):
    """Send gifs and stuff"""
    return redirect(f"https://discord.com/api/v9/gifs/search?provider={provider}&{request.query_string.decode()}", code=308)
