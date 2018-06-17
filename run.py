import logging
import asyncio

import asyncpg
from quart import Quart, g, jsonify

import config

from litecord.blueprints import gateway, auth
from litecord.errors import LitecordError

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def make_app():
    app = Quart(__name__)
    app.config.from_object(f'config.{config.MODE}')

    if app.config['DEBUG']:
        logging.basicConfig(level=logging.DEBUG)

    return app


app = make_app()
app.register_blueprint(gateway, url_prefix='/api/v6')
app.register_blueprint(auth, url_prefix='/api/v6')


@app.before_serving
async def app_before_serving():
    log.info('opening db')
    app.db = await asyncpg.create_pool(**app.config['POSTGRES'])
    g.app = app

    app.loop = asyncio.get_event_loop()
    g.loop = asyncio.get_event_loop()


@app.after_serving
async def app_after_serving():
    log.info('closing db')
    await app.db.close()


@app.errorhandler(LitecordError)
async def handle_litecord_err(err):
    return jsonify({
        'error': True,
        # 'code': err.code,
        'status': err.status_code,
        'message': err.message,
    }), err.status_code


@app.errorhandler(Exception)
def handle_exception(err):
    log.exception('Error happened in the app')
    return jsonify({
        'error': True,
        'message': repr(err)
    }), 500


@app.route('/')
async def index():
    return 'hewwo'
