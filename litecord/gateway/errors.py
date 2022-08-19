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

from litecord.errors import WebsocketClose


class GatewayError(WebsocketClose):
    def __init__(self, *args, **kwargs):
        super().__init__(4000, *args, **kwargs)


class UnknownOPCode(WebsocketClose):
    def __init__(self, *args, **kwargs):
        super().__init__(4001, *args, **kwargs)


class DecodeError(WebsocketClose):
    def __init__(self, *args, **kwargs):
        super().__init__(4002, *args, **kwargs)


class InvalidShard(WebsocketClose):
    def __init__(self, *args, **kwargs):
        super().__init__(4010, *args, **kwargs)


class ShardingRequired(WebsocketClose):
    def __init__(self, *args, **kwargs):
        super().__init__(4011, *args, **kwargs)
