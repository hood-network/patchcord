#!/usr/bin/env python3
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

import asyncio
import ssl
import sys
from typing import Any

import asyncpg
import logbook
import logging
import websockets
from quart import Response, jsonify
from logbook import StreamHandler, Logger
from logbook.compat import redirect_logging

from litecord.blueprints import (
    gateway,
    auth,
    users,
    guilds,
    channels,
    webhooks,
    misc,
    voice,
    invites,
    relationships,
    dms,
    icons,
    static,
    attachments,
    dm_channels,
    read_states,
    stickers,
    applications,
    store,
)

# those blueprints are separated from the "main" ones
# for code readability if people want to dig through
# the codebase.
from litecord.blueprints.guild import (
    guild_roles,
    guild_members,
    guild_channels,
    guild_mod,
    guild_emoji,
)

from litecord.blueprints.channel import (
    channel_messages,
    channel_reactions,
    channel_pins,
)

from litecord.blueprints.user import user_settings, user_billing, fake_store

from litecord.blueprints.user.billing_job import payment_job

from litecord.blueprints.admin_api import (
    voice as voice_admin,
    guilds as guilds_admin,
    users as users_admin,
    channels as channels_admin,
    info as info_admin,
    instance_invites,
)

from litecord.blueprints.admin_api.voice import guild_region_check

from litecord.ratelimits.handler import ratelimit_handler
from litecord.ratelimits.bucket import RatelimitBucket

from litecord.errors import BadRequest, LitecordError
from litecord.gateway.state_manager import StateManager
from litecord.storage import Storage
from litecord.user_storage import UserStorage
from litecord.dispatcher import EventDispatcher
from litecord.presence import PresenceManager
from litecord.images import IconManager
from litecord.jobs import JobManager
from litecord.voice.manager import VoiceManager
from litecord.guild_memory_store import GuildMemoryStore
from litecord.pubsub.lazy_guild import LazyGuildManager

from litecord.gateway.gateway import websocket_handler
from litecord.json import LitecordJSONProvider

from litecord.typing_hax import LitecordApp, request

# == HACKY PATCH ==
# this MUST be removed once Hypercorn gets py3.10 support.
from asyncio import start_server as _start_server

asyncio.start_server = lambda *args, loop=None, **kwargs: _start_server(*args, **kwargs)

# setup logbook
handler = StreamHandler(sys.stdout, level=logbook.INFO)
handler.push_application()
log = Logger("litecord.boot")
redirect_logging()


def make_app():
    app = LitecordApp(__name__)
    
    if app.is_debug:
        log.info("on debug")
        handler.level = logbook.DEBUG
        app.logger.level = logbook.DEBUG

    # always keep websockets on INFO
    logging.getLogger("websockets").setLevel(logbook.INFO)

    # use our custom json encoder for custom data types
    # do not move this anywhere else
    json_provider_class = LitecordJSONProvider

    return app


PREFIXES = ("/api", "/api/v5", "/api/v6", "/api/v7", "/api/v8", "/api/v9", "/api/v10")


def set_blueprints(app_: LitecordApp):
    """Set the blueprints for a given app instance"""
    bps = {
        gateway: None,
        auth: "/auth",
        users: "/users",
        user_settings: "/users",
        user_billing: "/users",
        relationships: "/users",
        guilds: "/guilds",
        guild_roles: "/guilds",
        guild_members: "/guilds",
        guild_channels: "/guilds",
        guild_mod: "/guilds",
        guild_emoji: "/guilds",
        channels: "/channels",
        channel_messages: "/channels",
        channel_reactions: "/channels",
        channel_pins: "/channels",
        webhooks: None,
        misc: None,
        voice: "/voice",
        invites: None,
        dms: "/users",
        dm_channels: "/channels",
        fake_store: None,
        icons: -1,
        attachments: -1,
        static: -1,
        info_admin: "/admin",
        voice_admin: "/admin/voice",
        guilds_admin: "/admin/guilds",
        users_admin: "/admin/users",
        channels_admin: "/admin/channels",
        instance_invites: "/admin/instance-invites",
        read_states: "",
        stickers: "",
        applications: "/applications",
        store: "/store",
    }

    for bp, suffix in bps.items():
        for prefix in PREFIXES:
            url_prefix = f'{prefix}{suffix or ""}'

            if suffix == -1:
                url_prefix = ""

            app_.register_blueprint(bp, url_prefix=url_prefix)


app = make_app()
set_blueprints(app)


@app.before_request
async def app_before_request():
    """Functions to call before the request actually
    takes place."""

    try:
        if not request.url_rule:
            raise ValueError
        request.discord_api_version = int(request.url_rule.rule.split("/api/v")[1].split("/")[0])
    except Exception:  # Default to 5 for ancient clients
        request.discord_api_version = 5
    finally:
        # check if api version is smaller than 5 or bigger than 10
        if 10 < request.discord_api_version < 5:
            raise BadRequest(50041)

    await ratelimit_handler()


@app.after_request
async def app_after_request(resp: Response):
    """Handle CORS headers."""
    origin = request.headers.get("Origin", "*")
    resp.headers["Access-Control-Allow-Origin"] = origin
    resp.headers["Access-Control-Allow-Headers"] = (
        "*, X-Super-Properties, "
        "X-Fingerprint, "
        "X-Context-Properties, "
        "X-Failed-Requests, "
        "X-Debug-Options, "
        "Content-Type, "
        "Authorization, "
        "Origin, "
        "If-None-Match"
    )
    resp.headers["Access-Control-Allow-Methods"] = resp.headers.get("allow", "*")

    return resp


def _set_rtl_reset(bucket: RatelimitBucket, resp: Response):
    reset = bucket._window + bucket.second
    precision = request.headers.get("x-ratelimit-precision", "millisecond")

    if precision == "second":
        resp.headers["X-RateLimit-Reset"] = str(round(reset))
    elif precision == "millisecond":
        resp.headers["X-RateLimit-Reset"] = str(reset)
    else:
        resp.headers["X-RateLimit-Reset"] = str(reset)


@app.after_request
async def app_set_ratelimit_headers(resp: Response):
    """Set the specific ratelimit headers."""
    try:
        bucket = request.bucket

        if bucket is None:
            return resp

        resp.headers["X-RateLimit-Limit"] = str(bucket.requests)
        resp.headers["X-RateLimit-Remaining"] = str(bucket._tokens)
        resp.headers["X-RateLimit-Global"] = str(request.bucket_global).lower()
        _set_rtl_reset(bucket, resp)

        # only add Retry-After if we actually hit a ratelimit
        retry_after = request.retry_after
        if request.retry_after:
            resp.headers["Retry-After"] = str(retry_after)
    except AttributeError:
        pass

    return resp


async def init_app_db(app_: LitecordApp):
    """Connect to databases.

    Also spawns the job scheduler.
    """
    log.info("db connect")
    pool = await asyncpg.create_pool(**app.config["POSTGRES"])
    assert pool is not None
    app_.db = pool
    app_.sched = JobManager(context_func=app.app_context)
    app.init_managers()

async def api_index(app_: LitecordApp):
    to_find = {}
    found = []

    with open("discord_endpoints.txt") as fd:
        for line in fd.readlines():
            components = line.split("  ")
            components = list(filter(bool, components))
            name, method, path = components
            path = f"/api/v6{path.strip()}"
            method = method.strip()
            to_find[(path, method)] = name

    for rule in app_.url_map._rules:
        path = rule.rule

        # convert the path to the discord_endpoints file's style
        path = path.replace("_", ".")
        path = path.replace("<", "{")
        path = path.replace(">", "}")
        path = path.replace("int:", "")

        # change our parameters into user.id
        path = path.replace("member.id", "user.id")
        path = path.replace("banned.id", "user.id")
        path = path.replace("target.id", "user.id")
        path = path.replace("other.id", "user.id")
        path = path.replace("peer.id", "user.id")

        methods = rule.methods
        if not methods: 
            continue
        for method in methods:
            pathname = to_find.get((path, method))
            if pathname:
                found.append(pathname)

    found = set(found)
    api = set(to_find.values())

    missing = api - found

    percentage = (len(found) / len(api)) * 100
    percentage = round(percentage, 2)

    log.debug(
        "API compliance: {} out of {} ({} missing), {}% compliant",
        len(found),
        len(api),
        len(missing),
        percentage,
    )

    log.debug("missing: {}", missing)


async def post_app_start(app_: LitecordApp):
    # we'll need to start a billing job
    app_.sched.spawn(payment_job())
    app_.sched.spawn(api_index(app_))
    app_.sched.spawn(guild_region_check())


def start_websocket(host, port, ws_handler) -> asyncio.Future:
    """Start a websocket. Returns the websocket future"""
    log.info(f"starting websocket at {host} {port}")

    async def _wrapper(ws, url):
        # We wrap the main websocket_handler
        # so we can pass quart's app object.
        await ws_handler(app, ws, url)

    kwargs = {"ws_handler": _wrapper, "host": host, "port": port}
    tls_cert_path = getattr(app.config, "WEBSOCKET_TLS_CERT_PATH", None)
    tls_key_path = getattr(app.config, "WEBSOCKET_TLS_CERT_PATH", None)
    if tls_cert_path:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(tls_cert_path, tls_key_path)
        kwargs["ssl"] = context

    return websockets.serve(**kwargs)


@app.before_serving
async def app_before_serving():
    """Callback for variable setup.

    Also sets up the websocket handlers.
    """
    log.info("opening db")
    await init_app_db(app)
    await post_app_start(app)

    # start gateway websocket
    # voice websocket is handled by the voice server
    ws_fut = start_websocket(
        app.config["WS_HOST"], app.config["WS_PORT"], websocket_handler
    )

    await ws_fut


@app.after_serving
async def app_after_serving():
    """Shutdown tasks for the server."""

    # first close all clients, then close db
    tasks = app.state_manager.gen_close_tasks()
    if tasks:
        await asyncio.wait(tasks)

    app.state_manager.close()

    app.sched.close()

    log.info("closing db")
    await app.db.close()


@app.errorhandler(LitecordError)
async def handle_litecord_err(error: Exception):
    assert isinstance(error, LitecordError)

    try:
        ejson = error.json
    except IndexError:
        ejson = {}

    log.warning("error: {} {!r}", error.status_code, error.message)

    data = {"code": error.error_code, "message": error.message, **ejson}
    if data["code"] == -1:
        data.pop("code")
    return jsonify(data), error.status_code


@app.errorhandler(404)
def handle_404(_):
    if request.path.startswith("/api"):
        return jsonify({"message": "404: Not Found", "code": 0}), 404
    return "Not Found", 404


@app.errorhandler(405)
def handle_405(_):
    return jsonify({"message": "405: Method Not Allowed", "code": 0}), 405


@app.errorhandler(413)
def handle_413(_):
    return jsonify({"message": "Request entity too large", "code": 40005}), 413


@app.errorhandler(500)
async def handle_500(_):
    return jsonify({"message": "500: Internal Server Error", "code": 0}), 500

if __name__ == "__main__":
    app.run()
