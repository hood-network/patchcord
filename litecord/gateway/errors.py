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
        super().__init__(*args, **kwargs)

        # hacky solution to
        # decrease code repetition
        self.args = [4000, self.args[0]]


class UnknownOPCode(WebsocketClose):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # hacky solution to
        # decrease code repetition
        self.args = [4001, self.args[0]]


class DecodeError(WebsocketClose):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.args = [4002, self.args[0]]


class InvalidShard(WebsocketClose):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.args = [4010, self.args[0]]


class ShardingRequired(WebsocketClose):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.args = [4011, self.args[0]]
