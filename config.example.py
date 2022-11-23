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

MODE = "Development"


class Config:
    """Default configuration values for Patchcord."""

    #: Main URL of the instance.
    MAIN_URL = "discordapp.io"

    #: Name of the instance
    NAME = "Patchcord/Nya"

    #: Enable debug logging?
    DEBUG = False

    #: Enable ssl?
    #  many routes will start giving https / wss
    #  urls depending of this config.
    IS_SSL = False

    #: Enable registrations in this instance?
    REGISTRATIONS = False

    # what to give on gateway route?
    # this must point to the websocket.

    # Set this url to somewhere *your users*
    # will hit the websocket.
    # e.g 'gateway.example.com' for reverse proxies.
    WEBSOCKET_URL = "localhost:5001"

    # Set these to file paths if you want to enable raw TLS support on
    # the websocket (without NGINX)
    WEBSOCKET_TLS_CERT_PATH = None
    WEBSOCKET_TLS_KEY_PATH = None

    #: Where to host the websocket?
    #  (a local address the server will bind to)
    WS_HOST = "0.0.0.0"
    WS_PORT = 5001

    #: Mediaproxy URL on the internet
    #  mediaproxy is made to prevent client IPs being leaked.
    #  None is a valid value if you don't want to deploy mediaproxy.
    MEDIA_PROXY = "localhost:5002"

    #: Postgres credentials
    POSTGRES = {}

    #: Shared secret for LVSP
    LVSP_SECRET = ""

    #: Default client build
    DEFAULT_BUILD = "latest"

    #: Secret for various things
    SECRET_KEY = "secret"


class Development(Config):
    DEBUG = True

    POSTGRES = {
        "host": "localhost",
        "user": "patchcord",
        "password": "123",
        "database": "patchcord",
    }


class Production(Config):
    DEBUG = False
    IS_SSL = True

    POSTGRES = {
        "host": "some_production_postgres",
        "user": "some_production_user",
        "password": "some_production_password",
        "database": "patchcord_or_anything_else_really",
    }
