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
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from litecord.typing_hax import app, request
else:
    from quart import current_app as app, request

def guild_view(guild_data: dict) -> dict:
    # Do all the below if applicable
    if request.discord_api_version < 8:
        if guild_data.get("roles"):
            guild_data["roles"] = list(map(role_view, guild_data["roles"]))
        if guild_data.get("channels"):
            guild_data["channels"] = list(map(channel_view, guild_data["channels"]))
    return guild_data


def message_view(message_data: dict) -> dict:
    # Change message type to 0 for unsupported types
    if request.discord_api_version < 8 and message_data["type"] in (19, 20, 23):
        message_data["type"] = 0
    message_data.pop("member", None)
    message_data.pop("guild_id", None)
    return message_data


def channel_view(channel_data: dict) -> dict:
    # Seperate permissions into permissions and permissions_new
    if request.discord_api_version < 8 and channel_data.get("permission_overwrites"):
        for overwrite in channel_data["permission_overwrites"]:
            overwrite["type"] = "role" if overwrite["type"] == 0 else "member"
            overwrite["allow_new"] = overwrite.get("allow", "0")
            overwrite["allow"] = (
                (int(overwrite["allow"]) & ((2 << 31) - 1))
                if overwrite.get("allow")
                else 0
            )
            overwrite["deny_new"] = overwrite.get("deny", "0")
            overwrite["deny"] = (
                (int(overwrite["deny"]) & ((2 << 31) - 1))
                if overwrite.get("deny")
                else 0
            )
    return channel_data


def role_view(role_data: dict) -> dict:
    # Seperate permissions into permissions and permissions_new
    if request.discord_api_version < 8:
        role_data["permissions_new"] = role_data["permissions"]
        role_data["permissions"] = int(role_data["permissions"]) & ((2 << 31) - 1)
    return role_data
