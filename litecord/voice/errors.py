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

from litecord.errors import WebsocketClose


class UnknownOPCode(WebsocketClose):
    close_code = 4000

class NotAuthenticated(WebsocketClose):
    close_code = 4003

class AuthFailed(WebsocketClose):
    close_code = 4004

class AlreadyAuth(WebsocketClose):
    close_code = 4005

class InvalidSession(WebsocketClose):
    close_code = 4006

class SessionTimeout(WebsocketClose):
    close_code = 4009

class ServerNotFound(WebsocketClose):
    close_code = 4011

class UnknownProtocol(WebsocketClose):
    close_code = 4012

class Disconnected(WebsocketClose):
    close_code = 4014

class VoiceServerCrash(WebsocketClose):
    close_code = 4015

class UnknownEncryption(WebsocketClose):
    close_code = 4016
