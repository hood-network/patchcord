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

MODE = "CI"


class Config:
    """Default configuration values for litecord."""

    MAIN_URL = "localhost:1"
    NAME = "gitlab ci"

    # Enable debug logging?
    DEBUG = False

    # Enable ssl? (gives wss:// instead of ws:// on gateway route)
    IS_SSL = False

    # what to give on gateway route?
    # this must point to the websocket.

    # Set this url to somewhere *your users*
    # will hit the websocket.
    # e.g 'gateway.example.com' for reverse proxies.
    WEBSOCKET_URL = "localhost:5001"

    # Where to host the websocket?
    # (a local address the server will bind to)
    WS_HOST = "localhost"
    WS_PORT = 5001

    # Postgres credentials
    POSTGRES = {}


class Development(Config):
    DEBUG = True
    POSTGRES = {
        "host": "localhost",
        "user": "litecord",
        "password": "123",
        "database": "litecord",
    }


class Production(Config):
    DEBUG = False
    IS_SSL = True


class CI(Config):
    DEBUG = True

    POSTGRES = {"host": "postgres", "user": "postgres", "password": ""}
