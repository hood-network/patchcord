import asyncio
import sys

import asyncpg
import logbook
import websockets
from quart import Quart, g, jsonify
from logbook import StreamHandler, Logger
from logbook.compat import redirect_logging

import config
from litecord.blueprints import gateway, auth, users, guilds, channels, \
    webhooks, science, voice
from litecord.gateway import websocket_handler
from litecord.errors import LitecordError
from litecord.gateway.state_manager import StateManager
from litecord.storage import Storage
from litecord.dispatcher import EventDispatcher

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

    return app


app = make_app()

bps = {
    gateway: None,
    auth: '/auth',
    users: '/users',
    guilds: '/guilds',
    channels: '/channels',
    webhooks: None,
    science: None,
    voice: '/voice'
}

for bp, suffix in bps.items():
    suffix = suffix or ''
    app.register_blueprint(bp, url_prefix=f'/api/v6{suffix}')


@app.after_request
async def app_after_request(resp):
    resp.headers['Access-Control-Allow-Origin'] = 'https://ptb.discordapp.com'
    resp.headers['Access-Control-Allow-Headers'] = ('*, X-Super-Properties, '
                                                    'X-Fingerprint, '
                                                    'X-Context-Properties, '
                                                    'X-Failed-Requests, '
                                                    'Content-Type')
    resp.headers['Access-Control-Allow-Methods'] = '*'
    return resp


@app.before_serving
async def app_before_serving():
    log.info('opening db')
    app.db = await asyncpg.create_pool(**app.config['POSTGRES'])
    g.app = app

    app.loop = asyncio.get_event_loop()
    g.loop = asyncio.get_event_loop()

    app.state_manager = StateManager()
    app.dispatcher = EventDispatcher(app.state_manager)
    app.storage = Storage(app.db)

    # start the websocket, etc
    host, port = app.config['WS_HOST'], app.config['WS_PORT']
    log.info(f'starting websocket at {host} {port}')

    async def _wrapper(ws, url):
        # We wrap the main websocket_handler
        # so we can pass quart's app object.
        await websocket_handler((app.db, app.state_manager, app.storage,
                                 app.loop, app.dispatcher), ws, url)

    ws_future = websockets.serve(_wrapper, host, port)

    await ws_future


@app.after_serving
async def app_after_serving():
    log.info('closing db')
    await app.db.close()


@app.errorhandler(LitecordError)
async def handle_litecord_err(err):
    try:
        ejson = err.json
    except IndexError:
        ejson = {}

    return jsonify({
        'error': True,
        # 'code': err.code,
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
    })


@app.route('/')
async def index():
    return 'hewwo'
