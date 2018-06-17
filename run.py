import logging

import asyncpg
from quart import Quart, g

import config

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def make_app():
    app = Quart(__name__)
    app.config.from_object(f'config.{config.MODE}')
    return app


app = make_app()


@app.before_serving
async def app_before_serving():
    log.info('opening db')
    app.db_pool = await asyncpg.create_pool(**app.config['POSTGRES'])


@app.after_serving
async def app_after_serving():
    log.info('closing db')
    await app.db_pool.close()


@app.route('/')
async def index():
    return 'hai'
