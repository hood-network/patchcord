"""

Litecord
Copyright (C) 2018-2019  Luna Mendes

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
import sys

import asyncpg
import logbook
import logging
import websockets
from quart import Quart, jsonify, request
from logbook import StreamHandler, Logger
from logbook.compat import redirect_logging
from aiohttp import ClientSession

# import the config set by instance owner
import config

from litecord.blueprints import (
    gateway, auth, users, guilds, channels, webhooks, science,
    voice, invites, relationships, dms, icons, nodeinfo, static,
    attachments, dm_channels
)

# those blueprints are separated from the "main" ones
# for code readability if people want to dig through
# the codebase.
from litecord.blueprints.guild import (
    guild_roles, guild_members, guild_channels, guild_mod,
    guild_emoji
)

from litecord.blueprints.channel import (
    channel_messages, channel_reactions, channel_pins
)

from litecord.blueprints.user import (
    user_settings, user_billing, fake_store
)

from litecord.blueprints.user.billing_job import payment_job

from litecord.blueprints.admin_api import (
    voice as voice_admin
)

from litecord.ratelimits.handler import ratelimit_handler
from litecord.ratelimits.main import RatelimitManager

from litecord.errors import LitecordError
from litecord.gateway.state_manager import StateManager
from litecord.storage import Storage
from litecord.user_storage import UserStorage
from litecord.dispatcher import EventDispatcher
from litecord.presence import PresenceManager
from litecord.images import IconManager
from litecord.jobs import JobManager
from litecord.voice.manager import VoiceManager

from litecord.gateway import websocket_handler

from litecord.utils import LitecordJSONEncoder

# setup logbook
handler = StreamHandler(sys.stdout, level=logbook.INFO)
handler.push_application()
log = Logger('litecord.boot')
redirect_logging()


def make_app():
    app = Quart(__name__)
    app.config.from_object(f'config.{config.MODE}')
    is_debug = app.config.get('DEBUG', False)
    app.debug = is_debug

    if is_debug:
        log.info('on debug')
        handler.level = logbook.DEBUG
        app.logger.level = logbook.DEBUG

    # always keep websockets on INFO
    logging.getLogger('websockets').setLevel(logbook.INFO)

    # use our custom json encoder for custom data types
    app.json_encoder = LitecordJSONEncoder

    return app


def set_blueprints(app_):
    """Set the blueprints for a given app instance"""
    bps = {
        gateway: None,
        auth: '/auth',

        users: '/users',
        user_settings: '/users',
        user_billing: '/users',
        relationships: '/users',

        guilds: '/guilds',
        guild_roles: '/guilds',
        guild_members: '/guilds',
        guild_channels: '/guilds',
        guild_mod: '/guilds',
        guild_emoji: '/guilds',

        channels: '/channels',
        channel_messages: '/channels',
        channel_reactions: '/channels',
        channel_pins: '/channels',

        webhooks: None,
        science: None,
        voice: '/voice',
        invites: None,
        dms: '/users',
        dm_channels: '/channels',

        fake_store: None,

        icons: -1,
        attachments: -1,
        nodeinfo: -1,
        static: -1,

        voice_admin: '/admin/voice'
    }

    for bp, suffix in bps.items():
        url_prefix = f'/api/v6{suffix or ""}'

        if suffix == -1:
            url_prefix = ''

        app_.register_blueprint(bp, url_prefix=url_prefix)


app = make_app()
set_blueprints(app)


@app.before_request
async def app_before_request():
    """Functions to call before the request actually
    takes place."""
    await ratelimit_handler()


@app.after_request
async def app_after_request(resp):
    """Handle CORS headers."""
    origin = request.headers.get('Origin', '*')
    resp.headers['Access-Control-Allow-Origin'] = origin
    resp.headers['Access-Control-Allow-Headers'] = (
        '*, X-Super-Properties, '
        'X-Fingerprint, '
        'X-Context-Properties, '
        'X-Failed-Requests, '
        'X-Debug-Options, '
        'Content-Type, '
        'Authorization, '
        'Origin, '
        'If-None-Match'
    )
    resp.headers['Access-Control-Allow-Methods'] = \
            resp.headers.get('allow', '*')

    return resp


@app.after_request
async def app_set_ratelimit_headers(resp):
    """Set the specific ratelimit headers."""
    try:
        bucket = request.bucket

        if bucket is None:
            raise AttributeError()

        resp.headers['X-RateLimit-Limit'] = str(bucket.requests)
        resp.headers['X-RateLimit-Remaining'] = str(bucket._tokens)
        resp.headers['X-RateLimit-Reset'] = str(bucket._window + bucket.second)

        resp.headers['X-RateLimit-Global'] = str(request.bucket_global).lower()

        # only add Retry-After if we actually hit a ratelimit
        retry_after = request.retry_after
        if request.retry_after:
            resp.headers['Retry-After'] = str(retry_after)
    except AttributeError:
        pass

    return resp


async def init_app_db(app_):
    """Connect to databases.

    Also spawns the job scheduler.
    """
    log.info('db connect')
    app_.db = await asyncpg.create_pool(**app.config['POSTGRES'])

    app_.sched = JobManager()


def init_app_managers(app_):
    """Initialize singleton classes."""
    app_.loop = asyncio.get_event_loop()
    app_.ratelimiter = RatelimitManager(app_.config.get('_testing'))
    app_.state_manager = StateManager()

    app_.storage = Storage(app_)
    app_.user_storage = UserStorage(app_.storage)

    app_.icons = IconManager(app_)

    app_.dispatcher = EventDispatcher(app_)
    app_.presence = PresenceManager(app_)

    app_.storage.presence = app_.presence

    app_.voice = VoiceManager(app_)


async def api_index(app_):
    to_find = {}
    found = []

    with open('discord_endpoints.txt') as fd:
        for line in fd.readlines():
            components = line.split('  ')
            components = list(filter(
                bool,
                components
            ))
            name, method, path = components
            path = f'/api/v6{path.strip()}'
            method = method.strip()
            to_find[(path, method)] = name

    for rule in app_.url_map.rules:
        path = rule.rule

        # convert the path to the discord_endpoints file's style
        path = path.replace('_', '.')
        path = path.replace('<', '{')
        path = path.replace('>', '}')
        path = path.replace('int:', '')

        # change our parameters into user.id
        path = path.replace('member.id', 'user.id')
        path = path.replace('banned.id', 'user.id')
        path = path.replace('target.id', 'user.id')
        path = path.replace('other.id', 'user.id')
        path = path.replace('peer.id', 'user.id')

        methods = rule.methods

        for method in methods:
            pathname = to_find.get((path, method))
            if pathname:
                found.append(pathname)

    found = set(found)
    api = set(to_find.values())

    missing = api - found

    percentage = (len(found) / len(api)) * 100
    percentage = round(percentage, 2)

    log.debug('API compliance: {} out of {} ({} missing), {}% compliant',
              len(found), len(api), len(missing), percentage)

    log.debug('missing: {}', missing)


async def post_app_start(app_):
    # we'll need to start a billing job
    app_.sched.spawn(payment_job(app_))
    app_.sched.spawn(api_index(app_))


def start_websocket(host, port, ws_handler) -> asyncio.Future:
    """Start a websocket. Returns the websocket future"""
    log.info(f'starting websocket at {host} {port}')

    async def _wrapper(ws, url):
        # We wrap the main websocket_handler
        # so we can pass quart's app object.
        await ws_handler(app, ws, url)

    return websockets.serve(_wrapper, host, port)


@app.before_serving
async def app_before_serving():
    """Callback for variable setup.

    Also sets up the websocket handlers.
    """
    log.info('opening db')
    await init_app_db(app)

    app.session = ClientSession()

    init_app_managers(app)
    await post_app_start(app)

    # start gateway websocket
    # voice websocket is handled by the voice server
    ws_fut = start_websocket(
        app.config['WS_HOST'], app.config['WS_PORT'],
        websocket_handler
    )

    await ws_fut


@app.after_serving
async def app_after_serving():
    """Shutdown tasks for the server."""

    # first close all clients, then close db
    tasks = app.state_manager.gen_close_tasks()
    if tasks:
        await asyncio.wait(tasks, loop=app.loop)

    app.state_manager.close()

    app.sched.close()

    log.info('closing db')
    await app.db.close()


@app.errorhandler(LitecordError)
async def handle_litecord_err(err):
    try:
        ejson = err.json
    except IndexError:
        ejson = {}

    try:
        ejson['code'] = err.error_code
    except AttributeError:
        pass

    return jsonify({
        'error': True,
        'status': err.status_code,
        'message': err.message,
        **ejson
    }), err.status_code


@app.errorhandler(500)
async def handle_500(err):
    return jsonify({
        'error': True,
        'message': repr(err),
        'internal_server_error': True,
    }), 500
