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
from aiofile import async_open as aopen
import aiohttp
import json
import time

bp = Blueprint("static", __name__)
try:
    with open('assets/builds.json') as f:
        BUILDS = json.load(f)
except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
    BUILDS = {}

ASSET_CACHE = {}


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
        "GIFT_CODE_HOST": f"{app.config['MAIN_URL']}/gifts",
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


def guess_content_type(file: str) -> str:
    file = file.lower()
    if file.endswith(".js"):
        return "text/javascript"
    elif file.endswith(".css"):
        return "text/css"
    elif file.endswith("json"):
        return "application/json"
    elif file.endswith(".svg"):
        return "image/svg"
    elif file.endswith(".png"):
        return "image/png"
    elif file.endswith(".jpg") or file.endswith(".jpeg"):
        return "image/jpeg"
    elif file.endswith(".gif"):
        return "image/gif"
    elif file.endswith(".woff"):
        return "font/woff"
    elif file.endswith(".woff2"):
        return "font/woff2"
    elif file.endswith(".wasm"):
        return "application/wasm"
    else:
        return "application/octet-stream"


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
                info = BUILDS[hash]
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

        if default:
            for asset in (scripts + styles):
                await _proxy_asset(asset, True)

        resp = await make_response(await render_template(file, **kwargs))
        if not default:
            resp.set_cookie("buildOverride", hash)
        elif request.cookies.get("buildOverride"):
            resp.set_cookie("buildOverride", "", expires=0)
        return resp


@bp.route("/launch", methods=["GET"])
@bp.route("/build", methods=["GET"])
async def load_latest_build():
    """Load the latest build."""
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


async def _proxy_asset(asset, default: bool = False):
    """Proxy asset requests to Discord."""
    if asset.startswith("version"):
        asset = "version.canary.json"

    fs_cache = False
    response = None
    data = None
    if asset in ASSET_CACHE:
        data = ASSET_CACHE[asset]

        response = await make_response(data["data"])
        response.headers["content-type"] = data["content-type"]
        if data.get("etag"):
            response.headers["etag"] = data["etag"]
        return response
    else:
        try:
            async with aopen(f"assets/{asset}") as f:
                data = (await f.read()).decode("utf-8")

                response = await make_response(data)
                response.headers["content-type"] = guess_content_type(asset)
        except FileNotFoundError:
            async with aiohttp.request("GET", f"https://canary.discord.com/assets/{asset}") as resp:
                if not 300 > resp.status >= 200:  # Fallback to the Wayback Machine if the asset is not found
                    async with aiohttp.request("GET", f"http://web.archive.org/web/0_if/discordapp.com/assets/{asset}") as resp:
                        if not 400 > resp.status >= 200:
                            return "Asset not found", 404
                        data = (await resp.read()).decode("utf-8")
                        fs_cache = True
                else:
                    data = (await resp.read()).decode("utf-8")

                # Here we patch the asset to replace various hardcoded values
                host = app.config["MAIN_URL"]
                main_url = ("https://" if app.config["IS_SSL"] else "http://") + host
                data = (data
                    # Hardcoded discord.com et al references
                    .replace("https://discord.com", main_url)
                    .replace('["discord.com/billing/promotions", "promos.discord.gg"]', f'["{host}/billing/promotions"]')
                    .replace('["discordapp.com/gifts", "discord.com/gifts"]', f'["{host}/gifts"]')
                    .replace('new Set(["canary.discord.com", "ptb.discord.com", "discord.com", "canary.discordapp.com", "ptb.discordapp.com", "discordapp.com"])', f'new Set(["{host}"])')
                    .replace(r'new RegExp("^https://(?:ptb\\.|canary\\.)?(discordapp|discord)\\.com/__development/link?[\\S]+$"', r'new RegExp("^https://%s/__development/link?[\\S]+$"' % host.replace(".", r"\\."))
                    .replace(r'/^((https:\/\/)?(discord\.gg\/)|(discord\.com\/)(invite\/)?)?[A-Za-z0-9]{8,8}$/', r'/^((https:\/\/)?(%s\/)(invite\/)?)?[A-Za-z0-9]{8,8}$/' % host.replace(".", r"\."))
                )

                response = await make_response(data)
                response.status = resp.status
                response.headers["content-type"] = resp.headers["content-type"]
                if "etag" in resp.headers:
                    response.headers["etag"] = resp.headers["etag"]

        if not response or not data:
            return "Asset not found", 404

        if default:
            for k, v in ASSET_CACHE.items():
                if v["default"]:
                    ASSET_CACHE.pop(k)

        if len([k for k, v in ASSET_CACHE.items() if not v["default"]]) > 250:
            for k, v in reversed(list(ASSET_CACHE.items())):
                if not v["default"]:
                    ASSET_CACHE.pop(k)
                    break

        ASSET_CACHE[asset] = {
            "data": data,
            "content-type": response.headers["content-type"],
            "etag": response.headers.get("etag"),
            "default": default,
        }

        if fs_cache:
            async with aopen(f"assets/{asset}", "w") as f:
                await f.write(data.encode("utf-8"))

        return response


@bp.route("/assets/<asset>", methods=["GET"])
async def proxy_assets(asset):
    """Proxy asset requests to Discord."""
    return await _proxy_asset(asset)
