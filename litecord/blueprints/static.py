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

from quart import Blueprint, current_app as app, render_template_string, render_template
from pathlib import Path
import aiohttp
import json
import time

bp = Blueprint("static", __name__)


@bp.route("/<path:path>")
async def static_pages(path):
    """Map requests from / to /static."""
    if ".." in path:
        return "no", 404

    static_path = Path.cwd() / Path("static") / path
    return await app.send_static_file(str(static_path))


@bp.route("/assets/<asset>")
async def proxy_asset(asset):
    """Proxy asset requests to Discord."""
    async with aiohttp.request("GET", f"https://canary.discord.com/assets/{asset}") as resp:
        return await resp.read(), resp.status, resp.headers


def _get_environment(app):
    return json.dumps({
        "API_ENDPOINT": f"//{app.config['MAIN_URL']}/api",
        "WEBAPP_ENDPOINT": f"//{app.config['MAIN_URL']}",
        "GATEWAY_ENDPOINT": "wss://" if app.config["IS_SSL"] else "ws://" + app.config["WEBSOCKET_URL"],
        "CDN_HOST": f"//{app.config['MAIN_URL']}",
        "ASSET_ENDPOINT": "https://" if app.config["IS_SSL"] else "http://" + app.config["MAIN_URL"],
        "MEDIA_PROXY_ENDPOINT": f"//{app.config['MEDIA_PROXY']}",
        "WIDGET_ENDPOINT": f"//{app.config['MAIN_URL']}/widget",
        "INVITE_HOST": f"{app.config['MAIN_URL']}/invite",
        "GUILD_TEMPLATE_HOST": f"{app.config['MAIN_URL']}/template",
        "GIFT_CODE_HOST": f"{app.config['MAIN_URL']}/gift",
        "RELEASE_CHANNEL": "staging",
        "MARKETING_ENDPOINT": f"//{app.config['MAIN_URL']}",
        "BRAINTREE_KEY": "production_5st77rrc_49pp2rp4phym7387",
        "STRIPE_KEY": "pk_live_CUQtlpQUF0vufWpnpUmQvcdi",
        "NETWORKING_ENDPOINT": f"//{app.config['MAIN_URL']}",
        "RTC_LATENCY_ENDPOINT": "//latency.discord.media/rtc",
        "ACTIVITY_APPLICATION_HOST": "discordsays.com",
        "PROJECT_ENV": "development",
        "REMOTE_AUTH_ENDPOINT": "//remote-auth-gateway.discord.gg",
        "SENTRY_TAGS": {
            "buildId": "7ea92cf",
            "buildType": "normal"
        },
        "MIGRATION_SOURCE_ORIGIN": "https://discordapp.com",
        "MIGRATION_DESTINATION_ORIGIN": "https://" if app.config["IS_SSL"] else "http://" + app.config["MAIN_URL"],
        "HTML_TIMESTAMP": int(time.time() * 1000),
        "ALGOLIA_KEY": "aca0d7082e4e63af5ba5917d5e96bed0"
    })


async def _load_build(hash: str = "latest"):
    """Load a build from discord.sale."""
    if hash == "latest":
        async with aiohttp.request("GET", "https://api.discord.sale/builds") as resp:
            if not resp.status == 200:
                return "Build not found", 404
            hash = await resp.json()[0]["hash"]

    async with aiohttp.request("GET", f"https://api.discord.sale/builds/{hash}") as resp:
        if not resp.status == 200:
            return "Build not found", 404

        info = await resp.json()
        scripts = [f"{file}.js" for file in info["files"]["root_scripts"]]
        styles = [f"{file}.css" for file in info["files"]["css"]]
        version = info["number"]

        kwargs = {
            'GLOBAL_ENV': _get_environment(app),
            "build_id": version,
            "style": styles[0],
            "loader": scripts[0],
            "classes": scripts[1]
        }

        if len(scripts) == 3:
            file = "old.html"
            kwargs["app"] = scripts[2]
        elif len(scripts) == 4:
            file = "new.html"
            kwargs["webpack"] = scripts[2]
            kwargs["app"] = scripts[3]
        else:
            return "Build not supported", 404

        return render_template(file, **kwargs)


@bp.route("/")
async def index_handler():
    """Handler for the index page."""
    return await _load_build(app.config['DEFAULT_BUILD'])


@bp.route("/build/<hash>")
async def build_handler(hash):
    """Load a specific build."""
    return await _load_build(hash)
