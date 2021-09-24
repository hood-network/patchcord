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

import secrets
from typing import Optional
from dataclasses import dataclass

from litecord.common.users import create_user, delete_user
from litecord.common.guilds import delete_guild, create_guild_channel
from litecord.blueprints.channel.messages import create_message
from litecord.blueprints.auth import make_token
from litecord.storage import int_
from litecord.enums import ChannelType, UserFlags
from litecord.errors import ChannelNotFound, MessageNotFound


def email() -> str:
    return f"{secrets.token_hex(5)}@{secrets.token_hex(5)}.com"


def random_email() -> str:
    # TODO: move everyone who uses email() to random_email()
    return email()


def random_username() -> str:
    return secrets.token_hex(10)


@dataclass
class WrappedUser:
    test_cli: "TestClient"
    id: int
    name: str
    discriminator: str
    avatar: Optional[str]
    flags: UserFlags
    public_flags: UserFlags
    bot: bool
    premium: bool
    bio: str
    accent_color: Optional[int]

    # secure fields
    email: str
    verified: str

    # extra-secure tokens (not here by default)
    password: Optional[str] = None
    password_hash: Optional[str] = None
    token: Optional[str] = None

    # not there by default
    premium_type: Optional[str] = None
    mobile: Optional[bool] = None
    phone: Optional[bool] = None
    mfa_enabled: Optional[bool] = None

    async def refetch(self) -> dict:
        async with self.test_cli.app.app_context():
            rjson = await self.test_cli.app.storage.get_user(self.id, secure=True)
            return WrappedUser.from_json(self.test_cli, rjson)

    async def delete(self):
        return await delete_user(self.id)

    @classmethod
    def from_json(cls, test_cli, data_not_owned):
        data = dict(data_not_owned)  # take ownership of data via copy
        data["name"] = data.pop("username")
        return cls(
            test_cli,
            **{
                **data,
                **{
                    "id": int(data["id"]),
                },
            },
        )


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
            guild = await self.test_cli.app.storage.get_guild_full(
                self.id, user_id=self.test_cli.user["id"]
            )
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


@dataclass
class WrappedGuildChannel:
    test_cli: "TestClient"
    id: int
    type: int
    guild_id: int
    parent_id: Optional[int]
    name: str
    position: int
    nsfw: bool
    topic: str
    rate_limit_per_user: int
    last_message_id: int
    permission_overwrites: list

    async def delete(self):
        async with self.test_cli.app.app_context():
            resp = await self.test_cli.delete(
                f"/api/v6/channels/{self.id}",
            )
            rjson = await resp.json

            if resp.status_code == 404 and rjson["code"] == ChannelNotFound.error_code:
                return

            assert resp.status_code == 200
            assert rjson["id"] == str(self.id)

    async def refetch(self) -> dict:
        async with self.test_cli.app.app_context():
            channel_data = await self.test_cli.app.storage.get_channel(self.id)
            return WrappedGuildChannel.from_json(self.test_cli, channel_data)

    @classmethod
    def from_json(cls, test_cli, rjson):
        return cls(
            test_cli,
            **{
                **rjson,
                **{
                    "id": int(rjson["id"]),
                    "guild_id": int(rjson["guild_id"]),
                    "parent_id": int_(rjson["parent_id"]),
                    "last_message_id": int_(rjson["last_message_id"]),
                    "rate_limit_per_user": int_(rjson["rate_limit_per_user"]),
                },
            },
        )


@dataclass
class WrappedMessage:
    test_cli: "TestClient"

    id: int
    channel_id: int
    author: dict

    type: int
    content: str

    timestamp: str
    edited_timestamp: str

    tts: bool
    mention_everyone: bool
    nonce: str
    embeds: list
    mentions: list
    mention_roles: list
    reactions: list
    attachments: list
    pinned: bool
    message_reference: Optional[dict]
    allowed_mentions: Optional[dict]
    member: Optional[dict] = None
    flags: Optional[int] = None
    guild_id: Optional[int] = None

    async def delete(self):
        async with self.test_cli.app.app_context():
            resp = await self.test_cli.delete(
                f"/api/v6/channels/{self.channel_id}/messages/{self.id}",
            )
            rjson = await resp.json

            if resp.status_code == 404 and rjson["code"] in (
                ChannelNotFound.error_code,
                MessageNotFound.error_code,
            ):
                return

            assert resp.status_code == 200
            assert rjson["id"] == str(self.id)

    async def refetch(self) -> Optional["WrappedMessage"]:
        async with self.test_cli.app.app_context():
            message_data = await self.test_cli.app.storage.get_message(self.id)
            if message_data is None:
                return None
            return WrappedMessage.from_json(self.test_cli, message_data)

    @classmethod
    def from_json(cls, test_cli, rjson):
        return cls(
            test_cli,
            **{
                **rjson,
                **{
                    "id": int(rjson["id"]),
                    "channel_id": int(rjson["channel_id"]),
                    "guild_id": int_(rjson["guild_id"]),
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
        username: Optional[str] = None,
        email: Optional[str] = None,
        password: Optional[str] = None,
    ) -> WrappedUser:
        username = username or random_username()
        email = email or random_email()
        password = password or random_username()

        async with self.app.app_context():
            user_id, password_hash = await create_user(username, email, password)
            user_token = make_token(user_id, password_hash)
            full_user_object = await self.app.storage.get_user(user_id, secure=True)

        return self.add_resource(
            WrappedUser.from_json(
                self,
                {
                    **full_user_object,
                    **{
                        "token": user_token,
                        "password_hash": password_hash,
                    },
                },
            )
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

    async def create_guild_channel(
        self,
        *,
        guild_id: int,
        name: Optional[str] = None,
        type: ChannelType = ChannelType.GUILD_TEXT,
        **kwargs,
    ) -> WrappedGuild:
        name = name or secrets.token_hex(6)
        channel_id = self.app.winter_factory.snowflake()

        async with self.app.app_context():
            await create_guild_channel(
                guild_id, channel_id, type, **{**{"name": name}, **kwargs}
            )
            channel_data = await self.app.storage.get_channel(channel_id)

        return self.add_resource(WrappedGuildChannel.from_json(self, channel_data))

    async def create_message(
        self,
        *,
        guild_id: int,
        channel_id: int,
        content: Optional[str] = None,
        author_id: Optional[int] = None,
    ) -> WrappedGuild:
        content = content or secrets.token_hex(6)
        author_id = author_id or self.user["id"]

        async with self.app.app_context():
            message_id = await create_message(
                channel_id,
                guild_id,
                author_id,
                {
                    "content": content,
                    "tts": False,
                    "nonce": 0,
                    "everyone_mention": False,
                    "embeds": [],
                    "message_reference": None,
                    "allowed_mentions": None,
                },
            )

            message_data = await self.app.storage.get_message(message_id)

        return self.add_resource(WrappedMessage.from_json(self, message_data))

    def _inject_auth(self, kwargs: dict) -> list:
        """Inject the test user's API key into the test request before
        passing the request on to the underlying TestClient."""
        headers = kwargs.get("headers", {})
        if "authorization" not in headers:
            headers["authorization"] = self.user["token"]
        if "as_user" in kwargs:
            headers["authorization"] = kwargs.pop("as_user").token
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
