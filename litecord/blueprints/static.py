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

from quart import Blueprint, current_app as app, render_template, make_response, request, abort
import aiohttp
import json
import time

bp = Blueprint("static", __name__)
try:
    with open('static/builds.json') as f:
        builds = json.load(f)
except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
    builds = {}


def _get_environment(app):
    return {
        "API_ENDPOINT": f"//{app.config['MAIN_URL']}/api",
        "API_VERSION": 9,
        "WEBAPP_ENDPOINT": f"//{app.config['MAIN_URL']}",
        "GATEWAY_ENDPOINT": ("wss://" if app.config["IS_SSL"] else "ws://") + app.config["WEBSOCKET_URL"],
        "CDN_HOST": f"//{app.config['MAIN_URL']}",
        "ASSET_ENDPOINT": ("https://" if app.config["IS_SSL"] else "http://") + app.config["MAIN_URL"],
        "MEDIA_PROXY_ENDPOINT": f"//{app.config['MEDIA_PROXY']}",
        "WIDGET_ENDPOINT": f"//{app.config['MAIN_URL']}/widget",
        "INVITE_HOST": f"{app.config['MAIN_URL']}/invite",
        "GUILD_TEMPLATE_HOST": f"{app.config['MAIN_URL']}/template",
        "GIFT_CODE_HOST": f"{app.config['MAIN_URL']}/gift",
        "RELEASE_CHANNEL": "staging",
        "MARKETING_ENDPOINT": f"//{app.config['MAIN_URL']}",
        "BRAINTREE_KEY": "production_5st77rrc_49pp2rp4phym7387",
        "STRIPE_KEY": "pk_test_A7jK4iCYHL045qgjjfzAfPxu",
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
        "MIGRATION_DESTINATION_ORIGIN": ("https://" if app.config["IS_SSL"] else "http://") + app.config["MAIN_URL"],
        "HTML_TIMESTAMP": int(time.time() * 1000),
        "ALGOLIA_KEY": "aca0d7082e4e63af5ba5917d5e96bed0"
    }


async def _load_build(hash: str = "latest", default: bool = False):
    """Load a build from discord.sale."""
    if hash == "latest":
        async with aiohttp.request("GET", "https://api.discord.sale/builds") as resp:
            if not 300 > resp.status >= 200:
                return "Bad Gateway", 502
            hash = (await resp.json())[0]["hash"]

    async with aiohttp.request("GET", f"https://api.discord.sale/builds/{hash}") as resp:
        if not 300 > resp.status >= 200:
            try:
                info = builds[hash]
            except KeyError:
                return "Build not found", 404
        else:
            info = await resp.json()

        scripts = [f"{file}.js" for file in info["files"]["rootScripts"]]
        styles = [f"{file}.css" for file in info["files"]["css"]]
        version = info["number"]

        kwargs = {
            "GLOBAL_ENV": _get_environment(app),
            "build_id": f" v{version}" if not default else "",
            "style": styles[0],
            "loader": scripts[0],
            "classes": scripts[1]
        }

        if len(scripts) == 2:
            file = "2016.html"
        elif len(scripts) == 3:
            file = "2018.html"
            kwargs["app"] = scripts[2]
        elif len(scripts) == 4:
            file = "2020.html"
            kwargs["webpack"] = scripts[2]
            kwargs["app"] = scripts[3]
        else:
            return "Build not supported", 404

        resp = await make_response(await render_template(file, **kwargs))
        if not default:
            resp.set_cookie("buildId", hash)
        elif request.cookies.get("buildId"):
            resp.set_cookie("buildId", "", expires=0)
        return resp


@bp.route("/launch", methods=["GET"])
@bp.route("/build", methods=["GET"])
async def load_latest_build():
    """Load a specific build."""
    return await _load_build()


@bp.route("/launch/<hash>", methods=["GET"])
@bp.route("/build/<hash>", methods=["GET"])
async def load_build(hash = "latest"):
    """Load a specific build."""
    return await _load_build(hash)


@bp.route("/", defaults={"path": ""}, methods=["GET"])
@bp.route("/<path:path>", methods=["GET"])
async def send_client(path):
    if path.startswith("api/"):
        return await abort(404)
    return await _load_build(request.cookies.get("build_id", app.config.get("DEFAULT_BUILD", "latest"), type=str), default=True)


@bp.route("/assets/<asset>", methods=["GET"])
async def proxy_asset(asset):
    """Proxy asset requests to Discord."""
    if asset.startswith("version"):
        asset = "version.canary.json"
    async with aiohttp.request("GET", f"https://canary.discord.com/assets/{asset}") as resp:
        if not 300 > resp.status >= 200:  # Fallback to the Wayback Machine if the asset is not found
            async with aiohttp.request("GET", f"http://web.archive.org/web/0_if/discordapp.com/assets/{asset}") as resp:
                if not 400 > resp.status >= 200:
                    return "Asset not found", 404
                response = await make_response(await resp.read())
        else:
            response = await make_response(await resp.read())

        response.status = resp.status
        response.headers["content-type"] = resp.headers["content-type"]
        if "etag" in resp.headers:
            response.headers["etag"] = resp.headers["etag"]
        return response
