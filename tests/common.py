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

import secrets
from typing import Optional
from dataclasses import dataclass

from litecord.common.users import create_user, delete_user
from litecord.common.guilds import delete_guild
from litecord.blueprints.auth import make_token
from litecord.storage import int_


def email() -> str:
    return f"{secrets.token_hex(5)}@{secrets.token_hex(5)}.com"


@dataclass
class WrappedUser:
    test_cli: "TestClient"
    id: int
    name: str
    email: str
    password: str
    token: str

    async def refetch(self) -> dict:
        async with self.test_cli.app.app_context():
            return await self.test_cli.app.storage.get_user(self.id)

    async def delete(self):
        return await delete_user(self.id)


@dataclass
class WrappedGuild:
    test_cli: "TestClient"
    id: int
    owner: bool  # value depends on the user that fetched guild
    owner_id: int
    name: str
    unavailable: bool
    icon: Optional[str]
    splash: Optional[str]
    region: Optional[str]
    afk_timeout: int
    afk_channel_id: Optional[str]
    afk_timeout: int
    verification_level: int
    default_message_notifications: int
    explicit_content_filter: int
    mfa_level: int
    embed_enabled: bool
    embed_channel_id: int
    widget_enabled: bool
    widget_channel_id: int
    system_channel_id: int
    rules_channel_id: int
    public_updates_channel_id: int
    features: str
    features: str
    banner: Optional[str]
    description: Optional[str]
    preferred_locale: Optional[str]
    discovery_splash: Optional[str]

    vanity_url_code: Optional[str]
    max_presences: int
    max_members: int
    guild_scheduled_events: list

    joined_at: str  # value depends on the user that fetched the guild

    member_count: int
    members: list
    channels: list
    roles: list
    presences: list
    emojis: list
    voice_states: list

    large: Optional[bool] = None

    async def delete(self):
        await delete_guild(self.id)

    async def refetch(self) -> "WrappedGuild":
        async with self.test_cli.app.app_context():
            guild = await self.test_cli.app.storage.get_guild_full(self.id)
            return WrappedGuild.from_json(self.test_cli, guild)

    @classmethod
    def from_json(cls, test_cli, rjson):
        return cls(
            test_cli,
            **{
                **rjson,
                **{
                    "id": int(rjson["id"]),
                    "owner_id": int(rjson["owner_id"]),
                    "afk_channel_id": int_(rjson["afk_channel_id"]),
                    "embed_channel_id": int_(rjson["embed_channel_id"]),
                    "widget_enabled": int_(rjson["widget_enabled"]),
                    "widget_channel_id": int_(rjson["widget_channel_id"]),
                    "system_channel_id": int_(rjson["system_channel_id"]),
                    "rules_channel_id": int_(rjson["rules_channel_id"]),
                    "public_updates_channel_id": int_(
                        rjson["public_updates_channel_id"]
                    ),
                },
            },
        )


class TestClient:
    """Test client wrapper class. Adds Authorization headers to all requests
    and manages test resource setup and destruction."""

    def __init__(self, test_cli, test_user):
        self.cli = test_cli
        self.app = test_cli.app
        self.user = test_user
        self.resources = []

    def __getitem__(self, key):
        return self.user[key]

    def add_resource(self, resource):
        self.resources.append(resource)
        return resource

    async def cleanup(self):
        for resource in self.resources:
            async with self.app.app_context():
                await resource.delete()

    async def create_user(
        self,
        *,
        username: str,
        email: str,
        password: Optional[str] = None,
    ) -> WrappedUser:
        password = password or secrets.token_hex(6)

        async with self.app.app_context():
            user_id, password_hash = await create_user(username, email, password)
            user_token = make_token(user_id, password_hash)

        return self.add_resource(
            WrappedUser(self, user_id, username, email, password, user_token)
        )

    async def create_guild(
        self,
        *,
        name: Optional[str] = None,
        region: Optional[str] = None,
        owner: Optional["WrappedUser"] = None,
    ) -> WrappedGuild:
        name = name or secrets.token_hex(6)
        owner_token = owner.token if owner else self.user["token"]

        async with self.app.app_context():
            # TODO move guild creation logic to litecord.common.guild
            # TODO make tests use aiosqlite on memory for db
            resp = await self.post(
                "/api/v6/guilds",
                json={"name": name, "region": region},
                headers={"authorization": owner_token},
            )
            rjson = await resp.json

        return self.add_resource(WrappedGuild.from_json(self, rjson))

    def _inject_auth(self, kwargs: dict) -> list:
        """Inject the test user's API key into the test request before
        passing the request on to the underlying TestClient."""
        headers = kwargs.get("headers", {})
        if "authorization" not in headers:
            headers["authorization"] = self.user["token"]
        return headers

    async def get(self, *args, **kwargs):
        """Send a GET request."""
        kwargs["headers"] = self._inject_auth(kwargs)
        return await self.cli.get(*args, **kwargs)

    async def post(self, *args, **kwargs):
        """Send a POST request."""
        kwargs["headers"] = self._inject_auth(kwargs)
        return await self.cli.post(*args, **kwargs)

    async def put(self, *args, **kwargs):
        """Send a POST request."""
        kwargs["headers"] = self._inject_auth(kwargs)
        return await self.cli.put(*args, **kwargs)

    async def patch(self, *args, **kwargs):
        """Send a PATCH request."""
        kwargs["headers"] = self._inject_auth(kwargs)
        return await self.cli.patch(*args, **kwargs)

    async def delete(self, *args, **kwargs):
        """Send a DELETE request."""
        kwargs["headers"] = self._inject_auth(kwargs)
        return await self.cli.delete(*args, **kwargs)
