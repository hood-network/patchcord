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

from .gateway import bp as gateway
from .auth import bp as auth
from .users import bp as users
from .guilds import bp as guilds
from .channels import bp as channels
from .webhooks import bp as webhooks
from .science import bp as science
from .voice import bp as voice
from .invites import bp as invites
from .relationships import bp as relationships
from .dms import bp as dms
from .icons import bp as icons
from .nodeinfo import bp as nodeinfo
from .static import bp as static
from .attachments import bp as attachments
from .dm_channels import bp as dm_channels
from .read_states import bp as read_states
from .stickers import bp as stickers
from .applications import bp as applications
from .store import bp as store

__all__ = [
    "gateway",
    "auth",
    "users",
    "guilds",
    "channels",
    "webhooks",
    "science",
    "voice",
    "invites",
    "relationships",
    "dms",
    "icons",
    "nodeinfo",
    "static",
    "attachments",
    "dm_channels",
    "read_states",
    "stickers",
    "applications",
    "store",
]
