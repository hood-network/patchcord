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

import asyncio
from typing import List, Dict, Any, Optional, TypedDict, cast, Iterable, TYPE_CHECKING
from xml.etree.ElementInclude import include

import aiohttp
from aiofile import async_open as aopen
from datetime import datetime, timedelta, date
from logbook import Logger
import json

from litecord.enums import ChannelType, MessageFlags, NSFWLevel
from litecord.common.messages import PLAN_ID_TO_TYPE
from litecord.blueprints.channel.reactions import (
    EmojiType,
    emoji_sql,
    partial_emoji,
    PartialEmoji,
)

from litecord.types import timestamp_
from litecord.json import pg_set_json
from litecord.presence import PresenceManager

if TYPE_CHECKING:
    from litecord.typing_hax import LitecordApp
else:
    from quart import Quart as LitecordApp

log = Logger(__name__)


def maybe(typ, val):
    return typ(val) if val is not None else None


def dict_(val):
    return maybe(dict, val)


def str_(val):
    return maybe(str, val)


def int_(val):
    return maybe(int, val)


def bool_(val):
    return maybe(int, val)


class EmojiStats(TypedDict):
    count: int
    me: bool
    emoji: PartialEmoji


class Storage:
    """Class for common SQL statements."""

    presence: PresenceManager

    def __init__(self, app: LitecordApp):
        self.app = app
        self.db = app.db
        self.stickers: Dict[int, dict] = {}

    async def fetchrow_with_json(self, query: str, *args) -> Any:
        """Fetch a single row with JSON/JSONB support."""
        # the pool by itself doesn't have
        # set_type_codec, so we must set it manually
        # by acquiring the connection
        async with self.db.acquire() as con:
            await pg_set_json(con)
            return await con.fetchrow(query, *args)

    async def fetch_with_json(self, query: str, *args) -> List[Any]:
        """Fetch many rows with JSON/JSONB support."""
        async with self.db.acquire() as con:
            await pg_set_json(con)
            return await con.fetch(query, *args)

    async def execute_with_json(self, query: str, *args) -> str:
        """Execute a SQL statement with JSON/JSONB support."""
        async with self.db.acquire() as con:
            await pg_set_json(con)
            return await con.execute(query, *args)

    async def parse_user(self, duser: dict, secure: bool) -> dict:
        duser["premium"] = duser.pop("premium_since") is not None
        duser["public_flags"] = duser["flags"]
        duser["banner_color"] = (
            hex(duser["accent_color"]).replace("0x", "#")
            if duser["accent_color"]
            else None
        )

        if secure:
            duser["desktop"] = True
            duser["mobile"] = False
            duser["phone"] = duser["phone"] if duser["phone"] else None

            today = date.today()
            born = duser.pop("date_of_birth")
            duser["nsfw_allowed"] = (
                (
                    (
                        today.year
                        - born.year
                        - ((today.month, today.day) < (born.month, born.day))
                    )
                    >= 18
                )
                if born
                else True
            )

            plan_id = await self.db.fetchval(
                """
            SELECT payment_gateway_plan_id
            FROM user_subscriptions
            WHERE status = 1
              AND user_id = $1
            """,
                int(duser["id"]),
            )

            duser["premium_type"] = PLAN_ID_TO_TYPE.get(plan_id)

        return duser

    async def get_user(self, user_id, secure: bool = False) -> Optional[Dict[str, Any]]:
        """Get a single user payload."""
        user_id = int(user_id)

        fields = [
            "id::text",
            "username",
            "discriminator",
            "avatar",
            "banner",
            "flags",
            "bot",
            "system",
            "premium_since",
            "bio",
            "accent_color",
            "pronouns",
            "avatar_decoration",
            "theme_colors",
        ]

        if secure:
            fields.extend(
                ["email", "verified", "mfa_enabled", "date_of_birth", "phone"]
            )

        user_row = await self.db.fetchrow(
            f"""
        SELECT {','.join(fields)}
        FROM users
        WHERE users.id = $1
        """,
            user_id,
        )

        if not user_row:
            return None

        return await self.parse_user(dict(user_row), secure)

    async def get_users(
        self,
        user_ids: Optional[List[int]] = None,
        secure: bool = False,
        extra_clause: str = "",
        where_clause: str = "WHERE id = ANY($1::bigint[])",
        args: Optional[List[Any]] = None,
    ) -> List[dict]:
        """Get many user payloads."""
        fields = [
            "id::text",
            "username",
            "discriminator",
            "avatar",
            "banner",
            "flags",
            "bot",
            "system",
            "premium_since",
            "bio",
            "accent_color",
            "pronouns",
            "avatar_decoration",
            "theme_colors",
        ]

        if secure:
            fields.extend(
                ["email", "verified", "mfa_enabled", "date_of_birth", "phone"]
            )

        users_rows = await self.db.fetch(
            f"""
            SELECT {','.join(fields)} {extra_clause}
            FROM users
            {where_clause}
            """,
            *(args or [user_ids if user_ids else []]),
        )

        return await asyncio.gather(
            *(self.parse_user(dict(user_row), secure) for user_row in users_rows)
        )

    async def search_user(self, username: str, discriminator: str) -> int:
        """Search a user"""
        if len(discriminator) < 4:
            # how do we do this in f-strings again..?
            discriminator = "%04d" % int(discriminator)

        return await self.db.fetchval(
            """
        SELECT id FROM users
        WHERE username = $1 AND discriminator = $2
        """,
            username,
            discriminator,
        )

    async def guild_features(self, guild_id: int) -> Optional[List[str]]:
        """Get a list of guild features for the given guild."""
        return await self.db.fetchval(
            """
        SELECT features FROM guilds
        WHERE id = $1
        """,
            guild_id,
        )

    async def vanity_invite(self, guild_id: int) -> Optional[str]:
        """Get the vanity invite for a guild."""
        return await self.db.fetchval(
            """
        SELECT code FROM vanity_invites
        WHERE guild_id = $1
        """,
            guild_id,
        )

    async def parse_guild(
        self,
        drow: dict,
        user_id: Optional[int],
        full: bool = False,
        large: Optional[int] = None,
    ) -> dict:
        """Parse guild payload."""
        guild_id = int(drow["id"])
        unavailable = self.app.guild_store.get(guild_id, "unavailable", False)
        if unavailable:
            return {"id": drow["id"], "unavailable": True}

        # guild.owner is dependant of the user doing the get_guild call.
        if user_id:
            drow["owner"] = drow["owner_id"] == str(user_id)

        drow["features"] = drow["features"] or []
        drow["roles"] = await self.get_role_data(guild_id)
        drow["emojis"] = await self.get_guild_emojis(guild_id)
        drow["vanity_url_code"] = await self.vanity_invite(guild_id)
        drow["nsfw"] = drow["nsfw_level"] in (
            NSFWLevel.RESTRICTED.value,
            NSFWLevel.EXPLICIT.value,
        )
        drow["embed_enabled"] = drow["widget_enabled"]
        drow["embed_channel_id"] = drow["widget_channel_id"]

        # hardcoding these since:
        #  - we aren't discord
        #  - the limit for guilds is unknown and heavily dependant on the hardware
        drow["max_presences"] = drow["max_members"] = drow[
            "max_video_channel_users"
        ] = drow["max_stage_video_channel_users"] = 1000000

        # TODO
        drow["preferred_locale"] = "en-US"
        drow["guild_scheduled_events"] = drow["embedded_activities"] = drow[
            "connections"
        ] = drow["stickers"] = []

        if full:
            return {**drow, **await self.get_guild_extra(guild_id, user_id, large)}
        return drow

    async def get_guild(
        self, guild_id: int, user_id: Optional[int] = None
    ) -> Optional[Dict]:
        """Get guild payload."""
        unavailable = self.app.guild_store.get(guild_id, "unavailable", False)
        if unavailable:
            return {"id": str(guild_id), "unavailable": True}

        row = await self.db.fetchrow(
            """
        SELECT id::text, owner_id::text, name, icon, splash,
               region, afk_channel_id::text, afk_timeout,
               verification_level, default_message_notifications, nsfw_level,
               explicit_content_filter, mfa_level,
               widget_enabled, widget_channel_id::text,
               system_channel_id::text, rules_channel_id::text, public_updates_channel_id::text, features,
               banner, description, preferred_locale, discovery_splash, premium_progress_bar_enabled
        FROM guilds
        WHERE guilds.id = $1
        """,
            guild_id,
        )
        if not row:
            return

        return await self.parse_guild(dict(row), user_id)

    async def get_guilds(
        self,
        guild_ids: Optional[List[int]] = None,
        user_id: Optional[int] = None,
        full: bool = False,
        extra_clause: str = "",
        where_clause: str = "WHERE id = ANY($1::bigint[])",
        args: Optional[Iterable[Any]] = None,
        large: Optional[int] = None,
    ) -> List[dict]:
        """Get many guild payloads."""
        rows = await self.db.fetch(
            f"""
            SELECT id::text, owner_id::text, name, icon, splash,
                   region, afk_channel_id::text, afk_timeout,
                   verification_level, default_message_notifications, nsfw_level,
                   explicit_content_filter, mfa_level,
                   embed_enabled, embed_channel_id::text,
                   widget_enabled, widget_channel_id::text,
                   system_channel_id::text, rules_channel_id::text, public_updates_channel_id::text, features,
                   banner, description, preferred_locale, discovery_splash, premium_progress_bar_enabled {extra_clause}
            FROM guilds
            {where_clause}
            """,
            *(args or [guild_ids if guild_ids else []]),
        )

        return await asyncio.gather(
            *(self.parse_guild(dict(row), user_id, full, large) for row in rows)
        )

    async def get_member_role_ids(self, guild_id: int, member_id: int) -> List[int]:
        """Get a list of role IDs that are on a member."""
        roles = await self.db.fetch(
            """
        SELECT role_id
        FROM member_roles
        WHERE guild_id = $1 AND user_id = $2
        """,
            guild_id,
            member_id,
        )

        roles = [r["role_id"] for r in roles]

        try:
            roles.remove(guild_id)
        except ValueError:
            # if the @everyone role isn't in, we add it
            # to member_roles automatically (it won't
            # be shown on the API, though).
            await self.db.execute(
                """
            INSERT INTO member_roles (user_id, guild_id, role_id)
            VALUES ($1, $2, $3)
            """,
                member_id,
                guild_id,
                guild_id,
            )

        return roles

    async def get_member(
        self, guild_id, member_id, with_user: bool = True
    ) -> Optional[Dict[str, Any]]:
        row = await self.db.fetchrow(
            """
        SELECT user_id, nickname AS nick, joined_at,
               deafened AS deaf, muted AS mute, avatar, banner, bio, pronouns,
               ARRAY(SELECT role_id::text FROM member_roles WHERE guild_id = $1 AND user_id = $2) AS roles
        FROM members
        WHERE guild_id = $1 and user_id = $2
        """,
            guild_id,
            member_id,
        )

        if row is None:
            return None

        drow = dict(row)

        try:
            drow["roles"].remove(str(guild_id))
        except ValueError:
            # We do a little DB repair
            await self.db.execute(
                """
            INSERT INTO member_roles (user_id, guild_id, role_id)
            VALUES ($1, $2, $3)
            """,
                member_id,
                guild_id,
                guild_id,
            )

        drow["joined_at"] = timestamp_(row["joined_at"])
        if with_user:
            drow["user"] = await self.get_user(member_id)
            drow.pop("user_id")
        else:
            drow["user_id"] = str(drow["user_id"])

        return drow

    async def get_member_multi(
        self, guild_id: int, user_ids: List[int]
    ) -> List[Dict[str, Any]]:
        """Get member information about multiple users in a guild."""
        members = []

        for user_id in user_ids:
            member = await self.get_member(guild_id, user_id)
            if not member:
                continue

            members.append(member)

        return members

    async def get_members(
        self, guild_id: int, with_user: bool = True
    ) -> Dict[int, Dict[str, Any]]:
        """Get member information on a guild."""
        members_basic = await self.db.fetch(
            """
        SELECT user_id, nickname AS nick, joined_at,
               deafened AS deaf, muted AS mute, avatar, banner, bio, pronouns,
               ARRAY(SELECT role_id::text FROM member_roles WHERE guild_id = $1 AND user_id = members.user_id) AS roles
        FROM members
        WHERE guild_id = $1
        """,
            guild_id,
        )

        members = {}
        for row in members_basic:
            drow = dict(row)
            user_id = drow.pop("user_id")

            try:
                drow["roles"].remove(str(guild_id))
            except ValueError:
                # We do a little DB repair
                await self.db.execute(
                    """
                INSERT INTO member_roles (user_id, guild_id, role_id)
                VALUES ($1, $2, $3)
                """,
                    user_id,
                    guild_id,
                    guild_id,
                )

            drow["joined_at"] = timestamp_(row["joined_at"])
            if with_user:
                drow["user"] = await self.get_user(user_id)
            else:
                drow["user_id"] = str(user_id)
            members[user_id] = drow

        return members

    async def query_members(self, guild_id: int, query: str, limit: int):
        """Find members with usernames matching the given query."""
        mids = await self.db.fetch(
            f"""
        SELECT user_id
        FROM members
        JOIN users ON members.user_id = users.id
        WHERE members.guild_id = $1
          AND users.username ILIKE '%'||$2
        LIMIT {limit}
        """,
            guild_id,
            query,
        )

        mids = [r["user_id"] for r in mids]
        members = await self.get_member_multi(guild_id, mids)
        return members

    async def chan_last_message(self, channel_id: int) -> Optional[int]:
        """Get the last message ID in a channel."""
        return await self.db.fetchval(
            """
        SELECT MAX(id)
        FROM messages
        WHERE channel_id = $1
        """,
            channel_id,
        )

    async def chan_last_message_str(self, channel_id: int) -> Optional[str]:
        """Get the last message ID but in a string.

        Doesn't convert when no last message ID is found.
        """
        last_msg = await self.chan_last_message(channel_id)
        return str_(last_msg)

    async def _channels_extra(self, row) -> Dict:
        """Fill in more information about a channel.

        Only works with guild channels, as they have
        base data and extra data.
        """
        channel_type = row["type"]
        chan_type = ChannelType(channel_type)

        if chan_type in (ChannelType.GUILD_TEXT, ChannelType.GUILD_NEWS):
            ext_row = await self.db.fetchrow(
                """
            SELECT topic, rate_limit_per_user
            FROM guild_text_channels
            WHERE id = $1
            """,
                row["id"],
            )

            drow = dict(ext_row)

            last_msg = await self.chan_last_message_str(row["id"])
            drow["last_message_id"] = last_msg

            return {**row, **drow}
        elif chan_type == ChannelType.GUILD_VOICE:
            vrow = await self.db.fetchrow(
                """
            SELECT bitrate, user_limit
            FROM guild_voice_channels
            WHERE id = $1
            """,
                row["id"],
            )

            return {**row, **dict(vrow)}
        else:
            return row

    async def get_chan_type(self, channel_id: int) -> Optional[int]:
        """Get the channel type integer, given channel ID."""
        return await self.db.fetchval(
            """
        SELECT channel_type
        FROM channels
        WHERE channels.id = $1
        """,
            channel_id,
        )

    async def chan_overwrites(
        self, channel_id: int, safe: bool = True
    ) -> List[Dict[str, Any]]:
        overwrite_rows = await self.db.fetch(
            f"""
        SELECT target_type, target_role, target_user, allow{'::text' if safe else ''}, deny{'::text' if safe else ''}
        FROM channel_overwrites
        WHERE channel_id = $1
        """,
            channel_id,
        )

        def _overwrite_convert(row):
            drow = dict(row)
            drow["type"] = drow.pop("target_type")
            drow["id"] = (
                str(drow.pop("target_role") or drow.pop("target_user"))
                if safe
                else (drow.pop("target_role") or drow.pop("target_user"))
            )
            drow.pop("target_user", None)

            return drow

        return list(map(_overwrite_convert, overwrite_rows))

    async def gdm_recipient_ids(self, channel_id: int) -> List[int]:
        """Get the list of user IDs that are recipients of the
        given Group DM."""
        user_ids = await self.db.fetch(
            """
        SELECT member_id
        FROM group_dm_members
        JOIN users
          ON member_id = users.id
        WHERE group_dm_members.id = $1
        ORDER BY username DESC
        """,
            channel_id,
        )

        return [r["member_id"] for r in user_ids]

    async def _gdm_recipients(
        self, channel_id: int, reference_id: Optional[int] = None
    ) -> List[Dict]:
        """Get the list of users that are recipients of the
        given Group DM."""
        recipients = await self.gdm_recipient_ids(channel_id)
        res = []

        for user_id in recipients:
            if user_id == reference_id:
                continue

            user = await self.get_user(user_id)

            if user is None:
                continue

            res.append(user)

        return res

    async def get_channel(self, channel_id: int, **kwargs) -> Optional[Dict[str, Any]]:
        """Fetch a single channel's information."""
        chan_type = await self.get_chan_type(channel_id)
        if chan_type is None:
            return None

        ctype = ChannelType(chan_type)

        if ctype in (
            ChannelType.GUILD_TEXT,
            ChannelType.GUILD_VOICE,
            ChannelType.GUILD_CATEGORY,
            ChannelType.GUILD_NEWS,
        ):
            base = await self.db.fetchrow(
                """
            SELECT id, guild_id::text, parent_id, name, position, nsfw, banner
            FROM guild_channels
            WHERE guild_channels.id = $1
            """,
                channel_id,
            )

            dbase = dict(base)
            dbase["type"] = chan_type

            res = await self._channels_extra(dbase)
            res["permission_overwrites"] = await self.chan_overwrites(channel_id)
            res["id"] = str(res["id"])
            if res["parent_id"]:
                res["parent_id"] = str(res["parent_id"])
            return res
        elif ctype == ChannelType.DM:
            dm_row = await self.db.fetchrow(
                """
            SELECT id, party1_id, party2_id
            FROM dm_channels
            WHERE id = $1
            """,
                channel_id,
            )

            drow = dict(dm_row)
            drow["type"] = chan_type

            drow["last_message_id"] = await self.chan_last_message_str(channel_id)

            # dms have just two recipients.
            drow["recipients"] = [
                await self.get_user(drow["party1_id"]),
                await self.get_user(drow["party2_id"]),
            ]

            drow.pop("party1_id")
            drow.pop("party2_id")

            drow["id"] = str(drow["id"])
            return drow
        elif ctype == ChannelType.GROUP_DM:
            gdm_row = await self.db.fetchrow(
                """
            SELECT id::text, owner_id::text, name, icon
            FROM group_dm_channels
            WHERE id = $1
            """,
                channel_id,
            )

            drow = dict(gdm_row)
            drow["type"] = chan_type

            user_id: Optional[int] = kwargs.get("user_id")
            drow["recipients"] = await self._gdm_recipients(channel_id, user_id)
            drow["last_message_id"] = await self.chan_last_message_str(channel_id)
            return drow

        raise RuntimeError(
            f"Data Inconsistency: Channel type {ctype} is not properly handled"
        )

    async def get_channel_ids(self, guild_id: int) -> List[int]:
        """Get all channel IDs in a guild."""
        rows = await self.db.fetch(
            """
        SELECT id
        FROM guild_channels
        WHERE guild_id = $1
        """,
            guild_id,
        )

        return [r["id"] for r in rows]

    async def get_channel_data(self, guild_id) -> List[Dict]:
        """Get channel list information on a guild"""
        channel_basics = await self.db.fetch(
            """
        SELECT id, guild_id::text, parent_id::text, name, position, nsfw
        FROM guild_channels
        WHERE guild_id = $1
        """,
            guild_id,
        )

        channels = []

        for row in channel_basics:
            ctype = await self.db.fetchval(
                """
            SELECT channel_type FROM channels
            WHERE id = $1
            """,
                row["id"],
            )

            drow = dict(row)
            drow["type"] = ctype

            res = await self._channels_extra(drow)
            res["permission_overwrites"] = await self.chan_overwrites(row["id"])
            res["id"] = str(res["id"])
            if res["parent_id"]:
                res["parent_id"] = str(res["parent_id"])
            channels.append(res)

        return channels

    async def get_role(
        self, role_id: int, guild_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """get a single role's information."""

        guild_field = "AND guild_id = $2" if guild_id else ""

        args = [role_id]
        if guild_id:
            args.append(guild_id)

        row = await self.db.fetchrow(
            f"""
        SELECT id::text, name, color, hoist, position,
               permissions::text, managed, mentionable
        FROM roles
        WHERE id = $1 {guild_field}
        LIMIT 1
        """,
            *args,
        )

        if not row:
            return None

        drow = dict(row)

        return drow

    async def get_role_data(self, guild_id: int) -> List[Dict[str, Any]]:
        """Get role list information on a guild."""
        roledata = await self.db.fetch(
            """
        SELECT id::text, name, color, hoist, position,
               permissions::text, managed, mentionable
        FROM roles
        WHERE guild_id = $1
        ORDER BY position ASC
        """,
            guild_id,
        )

        return list(map(dict, roledata))

    async def guild_voice_states(
        self, guild_id: int, user_id=None
    ) -> List[Dict[str, Any]]:
        """Get a list of voice states for the given guild."""
        channel_ids = await self.get_channel_ids(guild_id)
        if not user_id:
            return []
        res = []

        for channel_id in channel_ids:
            states = await self.app.voice.fetch_states(channel_id)
            jsonified = [s.as_json_for(user_id) for s in states.values()]

            # discord does NOT insert guild_id to voice states on the
            # guild voice state list.
            for state in jsonified:
                state.pop("guild_id")

            res.extend(jsonified)

        return res

    async def get_guild_extra(
        self, guild_id: int, user_id: Optional[int] = None, large: Optional[int] = None
    ) -> Dict:
        """Get extra information about a guild."""
        res = {}

        members = await self.get_members(guild_id)
        channels = await self.get_channel_data(guild_id)
        member_count = len(members)

        assert self.presence is not None
        if large:
            res["large"] = member_count > large

        if user_id:
            self_member = members.get(user_id)
            if self_member:
                res["joined_at"] = self_member["joined_at"]

        return {
            **res,
            **{
                "member_count": member_count,
                "members": list(members.values()),
                "channels": channels,
                "presences": await self.presence.guild_presences(members, guild_id),
                "voice_states": await self.guild_voice_states(guild_id),
                "lazy": True,
            },
        }

    async def get_guild_full(
        self, guild_id: int, user_id: Optional[int] = None, large_count: int = 250
    ) -> Optional[Dict]:
        """Get full information on a guild.

        This is a very expensive operation.
        """
        guild = await self.get_guild(guild_id, user_id)

        if guild is None:
            return None

        if guild.get("unavailable", False):
            return guild

        extra = await self.get_guild_extra(guild_id, user_id, large_count)
        return {**guild, **extra}

    async def guild_exists(self, guild_id: int) -> bool:
        """Return if a given guild ID exists."""
        id = await self.db.fetch(
            """
        SELECT id
        FROM guilds
        WHERE id = $1
        """,
            guild_id,
        )

        return id is not None

    async def get_member_ids(self, guild_id: int) -> List[int]:
        """Get member IDs inside a guild"""
        rows = await self.db.fetch(
            """
        SELECT user_id
        FROM members
        WHERE guild_id = $1
        """,
            guild_id,
        )

        return [r[0] for r in rows]

    async def _msg_regex(self, regex, func, content) -> List[Dict]:
        if content is None:
            return []

        res = []
        for match in regex.finditer(content):
            found_id = match.group(1)

            try:
                found_id = int(found_id)
            except ValueError:
                continue

            obj = await func(found_id)
            if obj is not None:
                res.append(obj)

        return res

    async def _inject_author(self, res: dict, _get_user):
        """Inject a pseudo-user object when the message is
        made by a webhook."""
        author_id = res["author_id"]

        # if author_id is None, we fetch webhook info
        # from the message_webhook_info table.
        if author_id is None:
            # webhook information in a message when made by a webhook
            # is copied from the webhook table, or inserted by the webhook
            # itself. this causes a complete disconnect from the messages
            # table into the webhooks table.
            wb_info = await self.db.fetchrow(
                """
            SELECT webhook_id, name, avatar
            FROM message_webhook_info
            WHERE message_id = $1
            """,
                int(res["id"]),
            )

            if not wb_info:
                log.warning("Webhook info not found for msg {}", res["id"])

            wb_info = wb_info or {
                "webhook_id": res["id"],
                "avatar": None,
                "name": "Unknown Webhook",
            }

            res["author"] = {
                "id": str(wb_info["webhook_id"]),
                "bot": True,
                "username": wb_info["name"],
                "avatar": wb_info["avatar"],
                "avatar_decoration": None,
                "discriminator": "0000",
                "public_flags": 0,
            }
            res["webhook_id"] = str(wb_info["webhook_id"])
        else:
            res["author"] = author = await _get_user(int(author_id))
            member = author.pop("member", None)
            if member:
                res["member"] = member

    async def parse_message(
        self,
        res: dict,
        user_id: Optional[int],
        include_member: bool,
        user_cache: Optional[dict] = None,
    ) -> dict:
        """Parse a message object."""
        user_cache = user_cache or {}

        res["id"] = str(res["id"])
        res["timestamp"] = timestamp_(res["timestamp"])
        res["edited_timestamp"] = timestamp_(res["edited_timestamp"])
        res["type"] = res.pop("message_type")
        res["content"] = res["content"] or ""
        res["pinned"] = bool(res["pinned"])
        res["mention_roles"] = (
            [str(r) for r in res["mention_roles"]] if res["mention_roles"] else []
        )

        guild_id = res["guild_id"]
        is_crosspost = (
            res["flags"] & MessageFlags.is_crosspost == MessageFlags.is_crosspost
        )
        attachments = list(res["attachments"]) if res["attachments"] else []
        reactions = list(res["reactions"]) if res["reactions"] else []

        if not guild_id:
            guild_id = await self.guild_from_channel(int(res["channel_id"]))
        res["guild_id"] = str(guild_id) if guild_id else None

        if res.get("message_reference") and not is_crosspost and include_member:
            message = await self.get_message(
                int(res["message_reference"]["message_id"]), user_id, include_member
            )
            res["referenced_message"] = message

        async def _get_user(user_id):
            try:
                user = user_cache[user_id]
            except KeyError:
                user = await self.get_user(user_id)
                if include_member and user and guild_id:
                    member = await self.get_member(guild_id, user_id, False)
                    if member:
                        user["member"] = member
                user_cache[user_id] = user
            return user

        await self._inject_author(res, _get_user)
        mentions = await asyncio.gather(*(_get_user(m) for m in res["mentions"]))
        res["mentions"] = [mention for mention in mentions if mention]

        emoji = []
        react_stats = {}
        for row in reactions:
            reactor_id, etype, eid, etext = row
            etype = EmojiType(etype)
            _, main_emoji = emoji_sql(etype, eid, etext)

            # Maintain reaction order
            emoji.append(main_emoji)
            try:
                stats = react_stats[main_emoji]
            except KeyError:
                stats = react_stats[main_emoji] = {
                    "count": 0,
                    "me": False,
                    "emoji": partial_emoji(etype, eid, etext),
                }

            stats["count"] += 1
            if reactor_id == user_id:
                stats["me"] = True

        # Return to original order
        res["reactions"] = list(map(react_stats.get, emoji))

        # If we're a crosspost, we need to inject the original attachments
        if is_crosspost and res.get("message_reference"):
            attachments = await self.db.fetch(
                """
            SELECT ROW(id::text, message_id, channel_id, filename, filesize, image, height, width)
            FROM attachments
            WHERE message_id = $1
                """,
                int(res["message_reference"]["message_id"]),
            )
            attachments = [dict(a) for a in attachments] if attachments else []

        a_res = []
        for attachment in attachments:
            # We have a ROW, so we need to convert it to a dict
            (
                a_id,
                a_message_id,
                a_channel_id,
                filename,
                filesize,
                image,
                height,
                width,
            ) = attachment
            attachment = {
                "id": a_id,
                "filename": filename,
                "size": filesize,
                "image": image,
                "height": height,
                "width": width,
            }
            # TODO: content_type
            proto = "https" if self.app.config["IS_SSL"] else "http"
            main_url = self.app.config["MAIN_URL"]
            attachment["url"] = (
                f"{proto}://{main_url}/attachments/"
                f"{a_channel_id}/{a_message_id}/"
                f"{filename}"
            )
            attachment["proxy_url"] = attachment["url"]
            if attachment["height"] is None:
                attachment.pop("height")
                attachment.pop("width")
            a_res.append(attachment)

        res["attachments"] = a_res

        sticker_ids = res.pop("sticker_ids")
        if sticker_ids:
            stickers = []
            for id in sticker_ids:
                sticker = await self.get_default_sticker(id)
                if sticker:
                    stickers.append(sticker)

            res["stickers"] = stickers
            res["sticker_items"] = [
                {
                    "format_type": sticker["format_type"],
                    "id": sticker["id"],
                    "name": sticker["name"],
                }
                for sticker in stickers
            ]

        res.pop("author_id")
        if not res["guild_id"]:
            res.pop("guild_id")
        if not res["nonce"]:
            res.pop("nonce")
        if not res["message_reference"]:
            res.pop("message_reference")
        if include_member and not res["reactions"]:
            res.pop("reactions")

        return res

    async def get_message(
        self,
        message_id: int,
        user_id: Optional[int] = None,
        include_member: bool = False,
    ) -> Optional[dict]:
        """Get a single message's payload."""
        message = await self.fetchrow_with_json(
            f"""
            SELECT id, channel_id::text, guild_id, author_id, content,
                created_at AS timestamp, edited_at AS edited_timestamp,
                tts, mention_everyone, nonce, message_type, embeds, flags,
                message_reference, sticker_ids, mentions, mention_roles,
                (SELECT message_id FROM channel_pins WHERE message_id = messages.id) AS pinned,
                ARRAY(SELECT ROW(id::text, message_id, channel_id, filename, filesize, image, height, width)
                    FROM attachments
                    WHERE message_id = messages.id)
                AS attachments,
                ARRAY(SELECT ROW(user_id, emoji_type, emoji_id, emoji_text)
                    FROM message_reactions
                    WHERE message_id = messages.id
                    ORDER BY react_ts
                ) AS reactions
            FROM messages
            WHERE id = $1
            """,
            message_id,
        )
        if message:
            return await self.parse_message(dict(message), user_id, include_member)

    async def get_messages(
        self,
        message_ids: Optional[List[int]] = None,
        user_id: Optional[int] = None,
        include_member: bool = False,
        extra_clause: str = "",
        where_clause: str = "WHERE id = ANY($1::bigint[])",
        args: Optional[Iterable[Any]] = None,
    ) -> List[dict]:
        """Get multiple messages' payloads."""
        rows = await self.fetch_with_json(
            f"""
            SELECT id, channel_id::text, guild_id, author_id, content,
                created_at AS timestamp, edited_at AS edited_timestamp,
                tts, mention_everyone, nonce, message_type, embeds, flags,
                message_reference, sticker_ids, mentions, mention_roles,
                (SELECT message_id FROM channel_pins WHERE message_id = messages.id) AS pinned,
                ARRAY(SELECT ROW(id::text, message_id, channel_id, filename, filesize, image, height, width)
                    FROM attachments
                    WHERE message_id = messages.id)
                AS attachments,
                ARRAY(SELECT ROW(user_id, emoji_type, emoji_id, emoji_text)
                    FROM message_reactions
                    WHERE message_id = messages.id
                    ORDER BY react_ts
                ) AS reactions
                {extra_clause}
            FROM messages
            {where_clause}
            """,
            *(args if args else [message_ids if message_ids else []]),
        )

        user_cache = {}
        return await asyncio.gather(
            *(
                self.parse_message(dict(row), user_id, include_member, user_cache)
                for row in rows
            )
        )

    async def get_invite(self, invite_code: str) -> Optional[Dict]:
        """Fetch invite information given its code."""
        invite = await self.db.fetchrow(
            """
        SELECT code, guild_id, channel_id, max_age, max_uses, uses, created_at
        FROM invites
        WHERE code = $1
        """,
            invite_code,
        )

        if invite is None:
            return None

        dinv = dict(invite)
        uses, max_age, max_uses = (
            dinv.pop("uses"),
            dinv.pop("max_age"),
            dinv.pop("max_uses"),
        )
        delta_sec = (datetime.utcnow() - dinv.pop("created_at")).total_seconds()

        if (max_age > 0 and delta_sec > max_age) or (max_uses > 0 and uses >= max_uses):
            await self.db.execute(
                """
            DELETE FROM invites
            WHERE code = $1
            """,
                invite_code,
            )
            return None

        # fetch some guild info
        guild = await self.db.fetchrow(
            """
        SELECT id::text, name, icon, splash, banner, features,
               verification_level, description, nsfw_level
        FROM guilds
        WHERE id = $1
        """,
            invite["guild_id"],
        )
        guild = dict(guild) if guild else None

        if guild:
            guild["vanity_url_code"] = await self.vanity_invite(invite["guild_id"])
            guild["nsfw"] = guild["nsfw_level"] in (
                NSFWLevel.RESTRICTED.value,
                NSFWLevel.EXPLICIT.value,
            )
            dinv["guild"] = dict(guild)
        else:
            dinv["guild"] = None

        chan = await self.get_channel(invite["channel_id"])

        if chan is None:
            return None

        dinv["channel"] = (
            {"id": chan["id"], "name": chan["name"], "type": chan["type"]}
            if chan
            else None
        )

        dinv["type"] = 0 if guild else (1 if chan else 2)

        dinv.pop("guild_id")
        dinv.pop("channel_id")

        return dinv

    async def get_invite_extra(
        self, invite_code: str, counts: bool = True, expiry: bool = False
    ) -> dict:
        """Extra information about the invite, such as
        approximate guild and presence counts."""
        data = {}

        if counts:
            guild_id = await self.db.fetchval(
                """
            SELECT guild_id
            FROM invites
            WHERE code = $1
            """,
                invite_code,
            )

            if guild_id is not None:
                data.update(await self.get_guild_counts(guild_id))
        if expiry:
            erow = await self.db.fetchrow(
                """
            SELECT created_at, max_age
            FROM invites
            WHERE code = $1
            """,
                invite_code,
            )

            data["expires_at"] = (
                timestamp_(erow["created_at"] + timedelta(seconds=erow["max_age"]))
                if erow["max_age"] > 0
                else None
            )

        return data

    async def get_invite_metadata(self, invite_code: str) -> Optional[Dict[str, Any]]:
        """Fetch invite metadata (max_age and friends)."""
        invite = await self.db.fetchrow(
            """
        SELECT code, inviter, created_at, uses,
               max_uses, max_age, temporary, created_at, revoked
        FROM invites
        WHERE code = $1
        """,
            invite_code,
        )

        if invite is None:
            return None

        dinv = dict(invite)
        inviter = await self.get_user(invite["inviter"])
        dinv["inviter"] = inviter
        dinv["expires_at"] = (
            timestamp_(invite["created_at"] + timedelta(seconds=invite["max_age"]))
            if invite["max_age"] > 0
            else None
        )
        dinv["created_at"] = timestamp_(invite["created_at"])

        return dinv

    async def get_guild_counts(self, guild_id: int) -> dict:
        """Fetch approximate member and presence counts for a guild."""
        members = await self.get_members(guild_id)
        assert self.presence is not None
        pres = await self.presence.guild_presences(members, guild_id)
        online_count = sum(1 for p in pres if p["status"] != "offline")

        return {
            "approximate_presence_count": online_count,
            "approximate_member_count": len(members),
        }

    async def get_dm(self, dm_id: int, user_id: Optional[int] = None) -> Optional[Dict]:
        """Get a DM channel."""
        dm_chan = await self.get_channel(dm_id, user_id=user_id)
        return dm_chan

    async def guild_from_channel(self, channel_id: int) -> int:
        """Get the guild id coming from a channel id."""
        return await self.db.fetchval(
            """
        SELECT guild_id
        FROM guild_channels
        WHERE id = $1
        """,
            channel_id,
        )

    async def get_dm_peer(self, channel_id: int, user_id: int) -> int:
        """Get the peer id on a dm"""
        parties = await self.db.fetchrow(
            """
        SELECT party1_id, party2_id
        FROM dm_channels
        WHERE id = $1 AND (party1_id = $2 OR party2_id = $2)
        """,
            channel_id,
            user_id,
        )

        parties = [parties["party1_id"], parties["party2_id"]]

        # get the id of the other party
        parties.remove(user_id)

        return parties[0]

    async def get_emoji(self, emoji_id: int) -> Optional[Dict[str, Any]]:
        """Get a single emoji."""
        row = await self.db.fetchrow(
            """
        SELECT id::text, name, animated, managed,
               require_colons, uploader_id
        FROM guild_emoji
        WHERE id = $1
        """,
            emoji_id,
        )

        if not row:
            return None

        drow = dict(row)

        # TODO
        drow["roles"] = []

        uploader_id = drow.pop("uploader_id")
        drow["user"] = await self.get_user(uploader_id)
        drow["available"] = True

        return drow

    async def get_guild_emojis(self, guild_id: int):
        """Get a list of all emoji objects in a guild."""
        rows = await self.db.fetch(
            """
        SELECT id
        FROM guild_emoji
        WHERE guild_id = $1
        """,
            guild_id,
        )

        emoji_ids = [r["id"] for r in rows]

        res = []

        for emoji_id in emoji_ids:
            emoji = await self.get_emoji(emoji_id)
            res.append(emoji)

        return res

    async def get_role_members(self, role_id: int) -> List[int]:
        """Get all members with a role."""
        rows = await self.db.fetch(
            """
        SELECT user_id
        FROM member_roles
        WHERE role_id = $1
        """,
            role_id,
        )

        return [r["user_id"] for r in rows]

    async def all_voice_regions(self) -> List[Dict[str, Any]]:
        """Return a list of all voice regions."""
        rows = await self.db.fetch(
            """
        SELECT id, name, vip, deprecated, custom
        FROM voice_regions
        """
        )

        return list(map(dict, rows))

    async def has_feature(self, guild_id: int, feature: str) -> bool:
        """Return if a certain guild has a certain feature."""
        features = await self.db.fetchval(
            """
        SELECT features FROM guilds
        WHERE id = $1
        """,
            guild_id,
        )
        if features is None:
            return False
        features = cast(List[str], features)
        return feature.upper() in features

    async def get_sticker_packs(self) -> dict:
        try:
            return await self.load_sticker_packs()
        except Exception:
            pass

        async with aiohttp.request(
            "GET",
            "https://discord.com/api/v9/sticker-packs",
            headers={"User-Agent": "DiscordBot (Litecord, Litecord)"},
        ) as r:
            r.raise_for_status()
            data = await r.json()
            await self.save_sticker_packs(data)
            return data

    async def load_sticker_packs(self):
        async with aopen("assets/sticker_packs.json", "r") as f:
            return json.loads(await f.read())

    async def save_sticker_packs(self, data):
        async with aopen("assets/sticker_packs.json", "w") as f:
            await f.write(json.dumps(data, separators=(",", ":")))

    async def get_default_sticker(self, sticker_id: int) -> Optional[dict]:
        if not self.stickers:
            stickers: Dict[Any, Any] = await self.get_sticker_packs()
            stickers = {"packs": {int(s["id"]): s for s in stickers["sticker_packs"]}}
            self.stickers = stickers
            for pack in stickers["packs"].values():
                stickers.update({int(s["id"]): s for s in pack["stickers"]})

        return self.stickers.get(sticker_id)

    async def get_experiments(self) -> List[list]:
        try:
            async with aopen("assets/experiments.json", "r") as f:
                return json.loads(await f.read())
        except (FileNotFoundError, json.decoder.JSONDecodeError, UnicodeDecodeError):
            return []

    async def get_guild_experiments(self) -> List[list]:
        try:
            async with aopen("assets/guild_experiments.json", "r") as f:
                return json.loads(await f.read())
        except (FileNotFoundError, json.decoder.JSONDecodeError, UnicodeDecodeError):
            return []
