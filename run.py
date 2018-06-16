import logging

import asyncpg
from quart import Quart, g

logging.basicConfig(level=logging.INFO)
app = Quart(__name__)


@app.route('/')
async def index():
    return 'hai'
