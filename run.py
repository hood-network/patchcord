import asyncio
import sys

import asyncpg
import logbook
import logging
import websockets
from quart import Quart, g, jsonify, request
from logbook import StreamHandler, Logger
from logbook.compat import redirect_logging

# import the config set by instance owner
import config

from litecord.blueprints import (
    gateway, auth, users, guilds, channels, webhooks, science,
    voice, invites, relationships, dms, icons, nodeinfo, static
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
    user_settings, user_billing
)

from litecord.blueprints.user.billing_job import (
    payment_job
)

from litecord.ratelimits.handler import ratelimit_handler
from litecord.ratelimits.main import RatelimitManager

from litecord.gateway import websocket_handler
from litecord.errors import LitecordError
from litecord.gateway.state_manager import StateManager
from litecord.storage import Storage
from litecord.user_storage import UserStorage
from litecord.dispatcher import EventDispatcher
from litecord.presence import PresenceManager
from litecord.images import IconManager
from litecord.jobs import JobManager

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

        icons: -1,
        nodeinfo: -1,
        static: -1
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
    origin = request.headers.get('Origin', '*')
    resp.headers['Access-Control-Allow-Origin'] = origin

    resp.headers['Access-Control-Allow-Headers'] = ('*, X-Super-Properties, '
                                                    'X-Fingerprint, '
                                                    'X-Context-Properties, '
                                                    'X-Failed-Requests, '
                                                    'X-Debug-Options, '
                                                    'Content-Type, '
                                                    'Authorization, '
                                                    'Origin, '
                                                    'If-None-Match')
    # resp.headers['Access-Control-Allow-Methods'] = '*'
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


async def init_app_db(app):
    """Connect to databases.

    Also spawns the job scheduler.
    """
    log.info('db connect')
    app.db = await asyncpg.create_pool(**app.config['POSTGRES'])

    app.sched = JobManager()


def init_app_managers(app):
    """Initialize singleton classes."""
    app.loop = asyncio.get_event_loop()
    app.ratelimiter = RatelimitManager(app.config.get('_testing'))
    app.state_manager = StateManager()

    app.storage = Storage(app.db)
    app.user_storage = UserStorage(app.storage)

    app.icons = IconManager(app)

    app.dispatcher = EventDispatcher(app)

    # TODO: only pass app
    app.presence = PresenceManager(
        app.storage, app.user_storage,
        app.state_manager, app.dispatcher
    )

    app.storage.presence = app.presence


async def api_index(app):
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

    for rule in app.url_map.rules:
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


async def post_app_start(app):
    # we'll need to start a billing job
    app.sched.spawn(payment_job(app))
    app.sched.spawn(api_index(app))


@app.before_serving
async def app_before_serving():
    log.info('opening db')
    await init_app_db(app)

    g.app = app
    g.loop = asyncio.get_event_loop()

    init_app_managers(app)

    # start the websocket, etc
    host, port = app.config['WS_HOST'], app.config['WS_PORT']
    log.info(f'starting websocket at {host} {port}')

    async def _wrapper(ws, url):
        # We wrap the main websocket_handler
        # so we can pass quart's app object.
        await websocket_handler(app, ws, url)

    ws_future = websockets.serve(_wrapper, host, port)

    await post_app_start(app)
    await ws_future


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
