"""

Litecord
Copyright (C) 2018  Luna Mendes

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

class LitecordError(Exception):
    status_code = 500

    @property
    def message(self):
        try:
            return self.args[0]
        except IndexError:
            return repr(self)

    @property
    def json(self):
        return self.args[1]


class BadRequest(LitecordError):
    status_code = 400


class Unauthorized(LitecordError):
    status_code = 401


class Forbidden(LitecordError):
    status_code = 403


class NotFound(LitecordError):
    status_code = 404


class GuildNotFound(NotFound):
    error_code = 10004


class ChannelNotFound(NotFound):
    error_code = 10003


class MessageNotFound(NotFound):
    error_code = 10008


class Ratelimited(LitecordError):
    status_code = 429


class MissingPermissions(Forbidden):
    error_code = 50013


class WebsocketClose(Exception):
    @property
    def code(self):
        return self.args[0]

    @property
    def reason(self):
        return self.args[1]
