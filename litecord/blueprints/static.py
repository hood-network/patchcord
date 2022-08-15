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

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate
from typing import Optional
from urllib.parse import quote, unquote
from wsgiref.handlers import format_date_time

import aiohttp
from aiofile import async_open as aopen
from litecord.auth import is_staff, token_check
from litecord.schemas import OVERRIDE_LINK, OVERRIDE_STAFF, validate
from quart import Blueprint, abort
from quart import current_app as app
from quart import jsonify, make_response, render_template, request

from ..utils import str_bool

bp = Blueprint("static", __name__)
try:
    with open("assets/builds.json", "r") as f:
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
    elif file.endswith(".ico"):
        return "image/x-icon"
    elif file.endswith(".woff"):
        return "font/woff"
    elif file.endswith(".woff2"):
        return "font/woff2"
    elif file.endswith(".wasm"):
        return "application/wasm"
    else:
        return "application/octet-stream"


async def _load_build(*, name: Optional[str] = None, hash: Optional[str] = None, default: bool = False, clear_override: bool = False):
    """Load a build from discord.sale."""
    value = hash if hash else name
    type = "branch" if hash else "id"

    if value == "latest":
        async with aiohttp.request("GET", "https://api.discord.sale/builds") as resp:
            if not 300 > resp.status >= 200:
                return "Bad Gateway", 502
            hash = (await resp.json())[0]["hash"]

    if not hash:
        return "Not Implemented", 501

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
        if clear_override:
            resp.set_cookie("buildOverride", "", expires=0)
        if not default and not (request.cookies.get("buildOverride") and not clear_override):
            resp.set_cookie(
                "buildOverride",
                await generate_build_override_cookie(
                    {"discord_web": {"type": type, "id": value}},
                    format_date_time(2147483647),
                ),
                expires=2147483647,
            )
        return resp


@bp.route("/launch", methods=["GET"])
@bp.route("/build", methods=["GET"])
@bp.route("/launch/latest", methods=["GET"])
@bp.route("/build/latest", methods=["GET"])
async def load_latest_build():
    """Load the latest build."""
    return await _load_build()


@bp.route("/launch/<hash>", methods=["GET"])
@bp.route("/build/<hash>", methods=["GET"])
async def load_build(hash):
    """Load a specific build."""
    return await _load_build(hash=hash)


@bp.route("/", defaults={"path": ""}, methods=["GET"])
@bp.route("/<path:path>", methods=["GET"])
async def send_client(path):
    if path.startswith("api/"):
        return await abort(404)

    cookie = request.cookies.get("buildOverride")
    if not cookie:
        return await _load_build(hash=app.config.get("DEFAULT_BUILD"), default=True, clear_override=True)

    signature, _, data = cookie.partition(".")
    info = verify(data, signature)
    if not info or datetime.now(tz=timezone.utc) > datetime(*parsedate(info["$meta"]["expiresAt"])[:6], tzinfo=timezone.utc):  # type: ignore
        return await _load_build(hash=app.config.get("DEFAULT_BUILD"), default=True, clear_override=True)

    if not info.get("discord_web"):
        return await _load_build(hash=app.config.get("DEFAULT_BUILD"), default=True, clear_override=False)

    if info["discord_web"]["type"] == "branch":
        return await _load_build(hash=info["discord_web"]["id"])
    elif info["discord_web"]["type"] == "id":
        return await _load_build(name=info["discord_web"]["id"])


async def _proxy_asset(asset, default: bool = False):
    """Proxy asset requests to Discord."""
    if asset.startswith("version"):
        asset = "version.canary.json"

    fs_cache = False
    response = None
    data = None
    if asset in ASSET_CACHE:
        data = ASSET_CACHE[asset]

        response = await make_response(data["data"], 200)
        response.headers["content-type"] = data["content-type"]
        if data.get("etag"):
            response.headers["etag"] = data["etag"]
        return response
    else:
        try:
            async with aopen(f"assets/{asset}") as f:
                data = await f.read()

                response = await make_response(data, 200)
                response.headers["content-type"] = guess_content_type(asset)
        except FileNotFoundError:
            async with aiohttp.request("GET", f"https://canary.discord.com/assets/{asset}") as resp:
                if not 300 > resp.status >= 200:  # Fallback to the Wayback Machine if the asset is not found
                    async with aiohttp.request("GET", f"http://web.archive.org/web/0_if/discordapp.com/assets/{asset}") as resp:
                        if not 400 > resp.status >= 200:
                            return "Asset not found", 404
                        data = await resp.read()
                        fs_cache = True
                else:
                    data = await resp.read()

                # Here we patch the asset to replace various hardcoded values
                host = app.config["MAIN_URL"]
                main_url = ("https://" if app.config["IS_SSL"] else "http://") + host
                if asset.endswith(".js"):
                    data = (data.decode("utf-8")
                        # Hardcoded discord.com et al references
                        .replace("https://discord.com", main_url)
                        .replace("https://discordapp.com", main_url)
                        .replace('["discord.com/billing/promotions","promos.discord.gg"]', f'["{host}/billing/promotions"]')
                        .replace('["discordapp.com/gifts","discord.com/gifts"]', f'["{host}/gifts"]')
                        .replace('["canary.discord.com","ptb.discord.com","discord.com","canary.discordapp.com","ptb.discordapp.com","discordapp.com"]', f'["{host}"]')
                        .replace('"discord.com"', f'"{host}"')
                        .replace('"discordapp.com"', f'"{host}"')
                        .replace('"discordapp.com/invite"', f'"{host}/invite"')
                        # Various regexes
                        .replace(r'RegExp("^https://(?:ptb\\.|canary\\.)?(discordapp|discord)\\.com/__development/link?[\\S]+$"', r'RegExp("^https://%s/__development/link?[\\S]+$"' % host.replace(".", r"\\."))
                        .replace(r'/^((https:\/\/)?(discord\.gg\/)|(discord\.com\/)(invite\/)?)?[A-Za-z0-9]{8,8}$/', r'/^((https:\/\/)?(%s\/)(invite\/)?)?[A-Za-z0-9]{8,8}$/' % host.replace(".", r"\."))
                        .replace('+"|discordapp.com|discord.com)$"', f'+"{host})$"')
                        .replace(r"/(?:^|\.)discordapp\.com$/i", r"/(?:^|\.)%s$/i" % host.replace(".", r"\."))
                        # Older build compatibility
                        .replace("r[t.type].push", "r[t.type]?.push")
                    )

                response = await make_response(data, resp.status)
                response.headers["content-type"] = resp.headers["content-type"]
                if "etag" in resp.headers:
                    response.headers["etag"] = resp.headers["etag"]

        if not response or not data:
            return "Asset not found", 404

        if default:
            for k, v in list(ASSET_CACHE.items()):
                if v["default"]:
                    ASSET_CACHE.pop(k, None)

        if len([k for k, v in ASSET_CACHE.items() if not v["default"]]) > 250:
            for k, v in reversed(list(ASSET_CACHE.items())):
                if not v["default"]:
                    ASSET_CACHE.pop(k, None)
                    break

        ASSET_CACHE[asset] = {
            "data": data,
            "content-type": response.headers["content-type"],
            "etag": response.headers.get("etag"),
            "default": default,
        }

        if fs_cache:
            async with aopen(f"assets/{asset}", "w") as f:
                await f.write(data)

        return response


@bp.route("/assets/<asset>", methods=["GET"])
async def proxy_assets(asset):
    """Proxy asset requests to Discord."""
    return await _proxy_asset(asset)


def sign(data: dict) -> str:
    """Sign a dict with the secret key."""
    dumped = json.dumps(data, separators=(",", ":"), sort_keys=True)
    return hmac.new(app.config.get("SECRET_KEY", "secret").encode("utf-8"), dumped.encode("utf-8"), hashlib.sha256).hexdigest()


def verify(data: str, signature: str) -> Optional[dict]:
    """Verify a signature."""
    # Verify the data is proper JSON
    try:
        data = json.dumps(json.loads(base64.b64decode(unquote(data) + '==')), separators=(",", ":"), sort_keys=True)
    except Exception:
        return
    if hmac.new(app.config.get("SECRET_KEY", "secret").encode("utf-8"), data.encode("utf-8"), hashlib.sha256).hexdigest() == unquote(signature):
        return json.loads(data)


async def generate_build_override_link(data: dict) -> str:
    """Generate a build override link."""
    j = validate(await request.get_json(), OVERRIDE_LINK)

    expiration = datetime.fromtimestamp(2147483647) if not j["meta"]["ttl_seconds"] else (datetime.now(tz=timezone.utc) + timedelta(seconds=j["meta"]["ttl_seconds"]))
    data = {"targetBuildOverride": j["overrides"], "releaseChannel": j["meta"]["release_channel"], "validForUserIds": [str(id) for id in j["meta"].get("valid_for_user_ids") or []], "allowLoggedOut": j["meta"]["allow_logged_out"], "expiresAt": format_date_time(time.mktime(expiration.timetuple()))}
    signature = sign(data)

    return ("https://" if app.config["IS_SSL"] else "http://") + f"{app.config['MAIN_URL']}/__development/link?s={quote(signature)}.{quote(base64.b64encode(json.dumps(data, separators=(',', ':'), sort_keys=True).encode('utf-8')).decode('utf-8'))}"


async def generate_build_override_cookie(data: dict, expiry: str) -> str:
    data["$meta"] = {"expiresAt": expiry}
    signature = sign(data)

    return f"{quote(signature)}.{quote(base64.b64encode(json.dumps(data, separators=(',', ':'), sort_keys=True).encode('utf-8')).decode('utf-8'))}"


@bp.route("/__development/create_build_override_link", methods=["POST"])
async def create_override_link():
    """Create a build override link."""
    user_id = await token_check()

    if not await is_staff(user_id):
        return "The maze wasn't meant for you", 403

    return jsonify({"url": await generate_build_override_link(await request.get_json())})


@bp.route("/__development/link", methods=["GET"])
async def get_override_link():
    """Get a build override."""
    data = request.args.get("s")
    meta = request.args.get("meta", type=str_bool)

    if not data:
        return "No payload provided.", 400

    signature, _, data = data.partition(".")
    info = verify(data, signature)
    if not info:
        return "Invalid payload!", 400

    if datetime.now(tz=timezone.utc) > datetime(*parsedate(info["expiresAt"])[:6], tzinfo=timezone.utc):  # type: ignore
        return "This link has expired. You will need to get a new one.", 400

    if meta:
        return jsonify(info)
    return await render_template("build_override.html", payload=unquote(data))


@bp.route("/__development/link", methods=["PUT"])
async def use_overrride_link():
    """Use a build override."""
    j = await request.get_json(silent=True)
    if not isinstance(j, dict) or not j.get("payload"):
        return "You must give this endpoint some json.", 415

    data = j["payload"]
    signature, _, data = data.partition(".")
    info = verify(data, signature)
    if not info:
        return {"message": "Invalid payload!"}, 400

    expires_at = datetime(*parsedate(info["expiresAt"])[:6], tzinfo=timezone.utc)  # type: ignore
    if datetime.now(tz=timezone.utc) > expires_at:
        return {"message": "This link has expired. You will need to get a new one."}, 400

    if not info["allowLoggedOut"]:
        token = j.get("token")
        if not token:
            return {"message": "A token is required."}, 400
        request.headers["Authorization"] = token
        user_id = await token_check(False)
        if not user_id:
            return {"message": f"Invalid token provided. You need to be logged into {app.config['NAME']} in this browser to use this link."}, 400
        if info["validForUserIds"] and str(user_id) not in info["validForUserIds"]:
            return {"message": "You are not authorized to use this link."}, 400

    resp = jsonify({"message": "Build overrides have been successfully applied!"})
    resp.set_cookie(
        "buildOverride",
        await generate_build_override_cookie(info["targetBuildOverride"], info["expiresAt"]),
        expires=expires_at,
    )
    return resp


@bp.route("/__development/build_overrides", methods=["GET"])
def get_build_overrides():
    """Get build overrides."""
    cookie = request.cookies.get("buildOverride")
    if not cookie:
        return jsonify({})

    signature, _, data = cookie.partition(".")
    info = verify(data, signature)
    if not info or datetime.now(tz=timezone.utc) > datetime(*parsedate(info["$meta"]["expiresAt"])[:6], tzinfo=timezone.utc):  # type: ignore
        resp = jsonify({})
        resp.set_cookie("buildOverride", "", expires=0)
        return resp

    info.pop("$meta")
    return jsonify(info)


@bp.route("/__development/build_overrides", methods=["PUT"])
async def set_build_overrides():
    """Set build overrides."""
    user_id = await token_check()
    if not await is_staff(user_id):
        return "The maze wasn't meant for you", 403

    j = validate(await request.get_json(), OVERRIDE_STAFF)
    if not j.get("overrides"):
        resp = await make_response("", 204)
        resp.set_cookie("buildOverride", "", expires=0)
        return resp

    resp = jsonify({"message": "Build overrides have been successfully applied!"})
    resp.set_cookie(
        "buildOverride",
        await generate_build_override_cookie(j["overrides"], format_date_time(2147483647)),
        expires=2147483647,
    )
    return resp


@bp.route("/__development/build_overrides", methods=["DELETE"])
async def remove_build_overrides():
    """Remove a build override."""
    resp = await make_response("", 204)
    resp.set_cookie("buildOverride", "", expires=0)
    return resp
