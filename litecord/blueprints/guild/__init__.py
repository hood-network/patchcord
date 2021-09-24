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

from .roles import bp as guild_roles
from .members import bp as guild_members
from .channels import bp as guild_channels
from .mod import bp as guild_mod
from .emoji import bp as guild_emoji

__all__ = ["guild_roles", "guild_members", "guild_channels", "guild_mod", "guild_emoji"]
