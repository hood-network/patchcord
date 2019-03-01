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
import os

import socket
import pytest

# this is very hacky.
sys.path.append(os.getcwd())

from run import app as main_app, set_blueprints

# pytest-sanic's unused_tcp_port can't be called twice since
# pytest fixtures etc etc.
def _unused_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


@pytest.fixture(name='app')
def _test_app(event_loop):
    set_blueprints(main_app)
    main_app.config['_testing'] = True

    # reassign an unused tcp port for websockets
    # since the config might give a used one.
    ws_port, vws_port = _unused_port(), _unused_port()
    print(ws_port, vws_port)

    main_app.config['WS_PORT'] = ws_port
    main_app.config['WEBSOCKET_URL'] = f'localhost:{ws_port}'

    main_app.config['VWS_PORT'] = vws_port
    main_app.config['VOICE_WEBSOCKET_URL'] = f'localhost:{vws_port}'

    # make sure we're calling the before_serving hooks
    event_loop.run_until_complete(main_app.startup())

    return main_app


@pytest.fixture(name='test_cli')
def _test_cli(app):
    """Give a test client."""
    return app.test_client()
