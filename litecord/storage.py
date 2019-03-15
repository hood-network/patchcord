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

from typing import List, Dict, Any, Optional

from logbook import Logger

from litecord.enums import ChannelType
from litecord.schemas import USER_MENTION, ROLE_MENTION
from litecord.blueprints.channel.reactions import (
    EmojiType, emoji_sql, partial_emoji
)

from litecord.blueprints.user.billing import PLAN_ID_TO_TYPE

from litecord.types import timestamp_
from litecord.utils import pg_set_json


log = Logger(__name__)


async def _dummy(any_id):
    return str(any_id)


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


def _filter_recipients(recipients: List[Dict[str, Any]], user_id: str):
    """Filter recipients in a list of recipients, removing
    the one that is reundant (ourselves)."""
    return list(filter(
        lambda recipient: recipient['id'] != user_id,
        recipients))


class Storage:
    """Class for common SQL statements."""
    def __init__(self, app):
        self.app = app
        self.db = app.db
        self.presence = None

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

    async def get_user(self, user_id, secure=False) -> Optional[Dict[str, Any]]:
        """Get a single user payload."""
        user_id = int(user_id)

        fields = ['id::text', 'username', 'discriminator',
                  'avatar', 'flags', 'bot', 'premium_since']

        if secure:
            fields.extend(['email', 'verified', 'mfa_enabled'])

        user_row = await self.db.fetchrow(f"""
        SELECT {','.join(fields)}
        FROM users
        WHERE users.id = $1
        """, user_id)

        if not user_row:
            return None

        duser = dict(user_row)

        duser['premium'] = duser['premium_since'] is not None
        duser.pop('premium_since')

        if secure:
            duser['mobile'] = False
            duser['phone'] = None

            plan_id = await self.db.fetchval("""
            SELECT payment_gateway_plan_id
            FROM user_subscriptions
            WHERE status = 1
              AND user_id = $1
            """, user_id)

            duser['premium_type'] = PLAN_ID_TO_TYPE.get(plan_id)

        return duser

    async def search_user(self, username: str, discriminator: str) -> int:
        """Search a user"""
        if len(discriminator) < 4:
            # how do we do this in f-strings again..?
            discriminator = '%04d' % int(discriminator)

        return await self.db.fetchval("""
        SELECT id FROM users
        WHERE username = $1 AND discriminator = $2
        """, username, discriminator)

    async def guild_features(self, guild_id: int) -> Optional[List[str]]:
        """Get a list of guild features for the given guild."""
        return await self.db.fetchval("""
        SELECT features FROM guilds
        WHERE id = $1
        """, guild_id)

    async def get_guild(self, guild_id: int, user_id=None) -> Optional[Dict]:
        """Get gulid payload."""
        row = await self.db.fetchrow("""
        SELECT id::text, owner_id::text, name, icon, splash,
               region, afk_channel_id::text, afk_timeout,
               verification_level, default_message_notifications,
               explicit_content_filter, mfa_level,
               embed_enabled, embed_channel_id::text,
               widget_enabled, widget_channel_id::text,
               system_channel_id::text, features,
               banner, description
        FROM guilds
        WHERE guilds.id = $1
        """, guild_id)

        if not row:
            return None

        drow = dict(row)

        if user_id:
            drow['owner'] = drow['owner_id'] == str(user_id)

        return drow

    async def _member_basic(self, guild_id: int, member_id: int):
        row = await self.db.fetchrow("""
        SELECT user_id, nickname, joined_at,
               deafened AS deaf, muted AS mute
        FROM members
        WHERE guild_id = $1 and user_id = $2
        """, guild_id, member_id)

        if row is None:
            return None

        row = dict(row)
        row['joined_at'] = timestamp_(row['joined_at'])
        return row

    async def _member_basic_with_roles(self, guild_id: int,
                                       member_id: int):
        basic = await self._member_basic(guild_id, member_id)

        if basic is None:
            return None

        basic = dict(basic)
        roles = await self.get_member_role_ids(guild_id, member_id)

        return {**basic, **{
            'roles': roles
        }}

    async def get_member_role_ids(self, guild_id: int,
                                  member_id: int) -> List[str]:
        """Get a list of role IDs that are on a member."""
        roles = await self.db.fetch("""
        SELECT role_id::text
        FROM member_roles
        WHERE guild_id = $1 AND user_id = $2
        """, guild_id, member_id)

        roles = [r['role_id'] for r in roles]

        try:
            roles.remove(str(guild_id))
        except ValueError:
            # if the @everyone role isn't in, we add it
            # to member_roles automatically (it won't
            # be shown on the API, though).
            await self.db.execute("""
            INSERT INTO member_roles (user_id, guild_id, role_id)
            VALUES ($1, $2, $3)
            """, member_id, guild_id, guild_id)

        return list(map(str, roles))

    async def _member_dict(self, row, guild_id, member_id) -> Dict[str, Any]:
        roles = await self.get_member_role_ids(guild_id, member_id)

        return {
            'user': await self.get_user(member_id),
            'nick': row['nickname'],

            # we don't send the @everyone role's id to
            # the user since it is known that everyone has
            # that role.
            'roles': roles,
            'joined_at': row['joined_at'],
            'deaf': row['deaf'],
            'mute': row['mute'],
        }

    async def get_member_data_one(self, guild_id: int,
                                  member_id: int) -> Optional[Dict[str, Any]]:
        """Get data about one member in a guild."""
        basic = await self._member_basic(guild_id, member_id)

        if not basic:
            return None

        return await self._member_dict(basic, guild_id, member_id)

    async def get_member_multi(self, guild_id: int,
                               user_ids: List[int]) -> List[Dict[str, Any]]:
        """Get member information about multiple users in a guild."""
        members = []

        for user_id in user_ids:
            member = await self.get_member_data_one(guild_id, user_id)

            if not member:
                continue

            members.append(member)

        return members

    async def get_member_data(self, guild_id: int) -> List[Dict[str, Any]]:
        """Get member information on a guild."""
        members_basic = await self.db.fetch("""
        SELECT user_id, nickname, joined_at,
               deafened AS deaf, muted AS mute
        FROM members
        WHERE guild_id = $1
        """, guild_id)

        members = []

        for row in members_basic:
            member = await self._member_dict(row, guild_id, row['user_id'])
            members.append(member)

        return members

    async def query_members(self, guild_id: int, query: str, limit: int):
        """Find members with usernames matching the given query."""
        mids = await self.db.fetch(f"""
        SELECT user_id
        FROM members
        JOIN users ON members.user_id = users.id
        WHERE members.guild_id = $1
          AND users.username LIKE '%'||$2
        LIMIT {limit}
        """, guild_id, query)

        mids = [r['user_id'] for r in mids]
        members = await self.get_member_multi(guild_id, mids)
        return members

    async def chan_last_message(self, channel_id: int):
        """Get the last message ID in a channel."""
        return await self.db.fetchval("""
        SELECT MAX(id)
        FROM messages
        WHERE channel_id = $1
        """, channel_id)

    async def chan_last_message_str(self, channel_id: int) -> str:
        """Get the last message ID but in a string.

        Converts to None (not the string "None") when
        no last message ID is found.
        """
        last_msg = await self.chan_last_message(channel_id)
        return str_(last_msg)

    async def _channels_extra(self, row) -> Dict:
        """Fill in more information about a channel."""
        channel_type = row['type']

        chan_type = ChannelType(channel_type)

        if chan_type == ChannelType.GUILD_TEXT:
            ext_row = await self.db.fetchrow("""
            SELECT topic, rate_limit_per_user
            FROM guild_text_channels
            WHERE id = $1
            """, row['id'])

            drow = dict(ext_row)

            last_msg = await self.chan_last_message_str(row['id'])

            drow['last_message_id'] = last_msg

            return {**row, **drow}

        if chan_type == ChannelType.GUILD_VOICE:
            vrow = await self.db.fetchrow("""
            SELECT bitrate, user_limit
            FROM guild_voice_channels
            WHERE id = $1
            """, row['id'])

            return {**row, **dict(vrow)}

        log.warning('unknown channel type: {}', chan_type)
        return row

    async def get_chan_type(self, channel_id: int) -> int:
        """Get the channel type integer, given channel ID."""
        return await self.db.fetchval("""
        SELECT channel_type
        FROM channels
        WHERE channels.id = $1
        """, channel_id)

    async def chan_overwrites(self, channel_id: int) -> List[Dict[str, Any]]:
        overwrite_rows = await self.db.fetch("""
        SELECT target_type, target_role, target_user, allow, deny
        FROM channel_overwrites
        WHERE channel_id = $1
        """, channel_id)

        def _overwrite_convert(row):
            drow = dict(row)

            target_type = drow['target_type']
            drow['type'] = 'user' if target_type == 0 else 'role'

            # if type is 0, the overwrite is for a user
            # if type is 1, the overwrite is for a role
            drow['id'] = {
                0: drow['target_user'],
                1: drow['target_role'],
            }[target_type]

            drow['id'] = str(drow['id'])

            drow.pop('target_type')
            drow.pop('target_user')
            drow.pop('target_role')

            return drow

        return list(map(_overwrite_convert, overwrite_rows))

    async def gdm_recipient_ids(self, channel_id: int) -> List[int]:
        """Get the list of user IDs that are recipients of the
        given Group DM."""
        user_ids = await self.db.fetch("""
        SELECT member_id
        FROM group_dm_members
        JOIN users
          ON member_id = users.id
        WHERE group_dm_members.id = $1
        ORDER BY username DESC
        """, channel_id)

        return [r['member_id'] for r in user_ids]

    async def _gdm_recipients(self, channel_id: int,
                              reference_id: int = None) -> List[Dict]:
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

    async def get_channel(self, channel_id: int,
                          **kwargs) -> Optional[Dict[str, Any]]:
        """Fetch a single channel's information."""
        chan_type = await self.get_chan_type(channel_id)
        ctype = ChannelType(chan_type)

        if ctype in (ChannelType.GUILD_TEXT,
                     ChannelType.GUILD_VOICE,
                     ChannelType.GUILD_CATEGORY):
            base = await self.db.fetchrow("""
            SELECT id, guild_id::text, parent_id, name, position, nsfw
            FROM guild_channels
            WHERE guild_channels.id = $1
            """, channel_id)

            dbase = dict(base)
            dbase['type'] = chan_type

            res = await self._channels_extra(dbase)
            res['permission_overwrites'] = await self.chan_overwrites(
                channel_id)

            res['id'] = str(res['id'])
            return res
        elif ctype == ChannelType.DM:
            dm_row = await self.db.fetchrow("""
            SELECT id, party1_id, party2_id
            FROM dm_channels
            WHERE id = $1
            """, channel_id)

            drow = dict(dm_row)
            drow['type'] = chan_type

            drow['last_message_id'] = await self.chan_last_message_str(
                channel_id
            )

            # dms have just two recipients.
            drow['recipients'] = [
                await self.get_user(drow['party1_id']),
                await self.get_user(drow['party2_id'])
            ]

            drow.pop('party1_id')
            drow.pop('party2_id')

            drow['id'] = str(drow['id'])
            return drow
        elif ctype == ChannelType.GROUP_DM:
            gdm_row = await self.db.fetchrow("""
            SELECT id::text, owner_id::text, name, icon
            FROM group_dm_channels
            WHERE id = $1
            """, channel_id)

            drow = dict(gdm_row)
            drow['type'] = chan_type
            drow['recipients'] = await self._gdm_recipients(
                channel_id, kwargs.get('user_id')
            )
            drow['last_message_id'] = await self.chan_last_message_str(
                channel_id
            )

            return drow

        return None

    async def get_channel_ids(self, guild_id: int) -> List[int]:
        """Get all channel IDs in a guild."""
        rows = await self.db.fetch("""
        SELECT id
        FROM guild_channels
        WHERE guild_id = $1
        """, guild_id)

        return [r['id'] for r in rows]

    async def get_channel_data(self, guild_id) -> List[Dict]:
        """Get channel list information on a guild"""
        channel_basics = await self.db.fetch("""
        SELECT id, guild_id::text, parent_id::text, name, position, nsfw
        FROM guild_channels
        WHERE guild_id = $1
        """, guild_id)

        channels = []

        for row in channel_basics:
            ctype = await self.db.fetchval("""
            SELECT channel_type FROM channels
            WHERE id = $1
            """, row['id'])

            drow = dict(row)
            drow['type'] = ctype

            res = await self._channels_extra(drow)

            res['permission_overwrites'] = await self.chan_overwrites(
                row['id'])

            # Making sure.
            res['id'] = str(res['id'])
            channels.append(res)

        return channels

    async def get_role(self, role_id: int,
                       guild_id: int = None) -> Optional[Dict[str, Any]]:
        """get a single role's information."""

        guild_field = 'AND guild_id = $2' if guild_id else ''

        args = [role_id]
        if guild_id:
            args.append(guild_id)

        row = await self.db.fetchrow(f"""
        SELECT id::text, name, color, hoist, position,
               permissions, managed, mentionable
        FROM roles
        WHERE id = $1 {guild_field}
        LIMIT 1
        """, *args)

        if not row:
            return None

        return dict(row)

    async def get_role_data(self, guild_id: int) -> List[Dict[str, Any]]:
        """Get role list information on a guild."""
        roledata = await self.db.fetch("""
        SELECT id::text, name, color, hoist, position,
               permissions, managed, mentionable
        FROM roles
        WHERE guild_id = $1
        ORDER BY position ASC
        """, guild_id)

        return list(map(dict, roledata))

    async def guild_voice_states(self, guild_id: int,
                                 user_id=None) -> List[Dict[str, Any]]:
        """Get a list of voice states for the given guild."""
        channel_ids = await self.get_channel_ids(guild_id)

        res = []

        for channel_id in channel_ids:
            states = await self.app.voice.fetch_states(channel_id)

            jsonified = [s.as_json_for(user_id) for s in states.values()]

            # discord does NOT insert guild_id to voice states on the
            # guild voice state list.
            for state in jsonified:
                state.pop('guild_id')

            res.extend(jsonified)

        return res

    async def get_guild_extra(self, guild_id: int,
                              user_id=None, large=None) -> Dict:
        """Get extra information about a guild."""
        res = {}

        member_count = await self.db.fetchval("""
        SELECT COUNT(*)
        FROM members
        WHERE guild_id = $1
        """, guild_id)

        if large:
            res['large'] = member_count > large

        if user_id:
            joined_at = await self.db.fetchval("""
            SELECT joined_at
            FROM members
            WHERE guild_id = $1 AND user_id = $2
            """, guild_id, user_id)

            res['joined_at'] = timestamp_(joined_at)

        members = await self.get_member_data(guild_id)
        channels = await self.get_channel_data(guild_id)
        roles = await self.get_role_data(guild_id)

        mids = [int(m['user']['id']) for m in members]

        return {**res, **{
            'member_count': member_count,
            'members': members,
            'channels': channels,
            'roles': roles,

            'presences': await self.presence.guild_presences(
                mids, guild_id
            ),

            'emojis': await self.get_guild_emojis(guild_id),
            'voice_states': await self.guild_voice_states(guild_id),
        }}

    async def get_guild_full(self, guild_id: int, user_id: Optional[int] = None,
                             large_count: int = 250) -> Optional[Dict]:
        """Get full information on a guild.

        This is a very expensive operation.
        """
        guild = await self.get_guild(guild_id, user_id)

        if guild is None:
            return None

        extra = await self.get_guild_extra(guild_id, user_id, large_count)

        return {**guild, **extra}

    async def guild_exists(self, guild_id: int) -> bool:
        """Return if a given guild ID exists."""
        owner_id = await self.db.fetch("""
        SELECT owner_id
        FROM guilds
        WHERE id = $1
        """, guild_id)

        return owner_id is not None

    async def get_member_ids(self, guild_id: int) -> List[int]:
        """Get member IDs inside a guild"""
        rows = await self.db.fetch("""
        SELECT user_id
        FROM members
        WHERE guild_id = $1
        """, guild_id)

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

    async def get_reactions(self, message_id: int, user_id=None) -> List:
        """Get all reactions in a message."""
        reactions = await self.db.fetch("""
        SELECT user_id, emoji_type, emoji_id, emoji_text
        FROM message_reactions
        WHERE message_id = $1
        ORDER BY react_ts
        """, message_id)

        # ordered list of emoji
        emoji = []

        # the current state of emoji info
        react_stats = {}

        # to generate the list, we pass through all
        # all reactions and insert them all.

        # we can't use a set() because that
        # doesn't guarantee any order.
        for row in reactions:
            etype = EmojiType(row['emoji_type'])
            eid, etext = row['emoji_id'], row['emoji_text']

            # get the main key to use, given
            # the emoji information
            _, main_emoji = emoji_sql(etype, eid, etext)

            if main_emoji in emoji:
                continue

            # maintain order (first reacted comes first
            # on the reaction list)
            emoji.append(main_emoji)

            react_stats[main_emoji] = {
                'count': 0,
                'me': False,
                'emoji': partial_emoji(etype, eid, etext)
            }

        # then the 2nd pass, where we insert
        # the info for each reaction in the react_stats
        # dictionary
        for row in reactions:
            etype = EmojiType(row['emoji_type'])
            eid, etext = row['emoji_id'], row['emoji_text']

            # same thing as the last loop,
            # extracting main key
            _, main_emoji = emoji_sql(etype, eid, etext)

            stats = react_stats[main_emoji]
            stats['count'] += 1

            if row['user_id'] == user_id:
                stats['me'] = True

        # after processing reaction counts,
        # we get them in the same order
        # they were defined in the first loop.
        return list(map(react_stats.get, emoji))

    async def get_attachments(self, message_id: int) -> List[Dict[str, Any]]:
        """Get a list of attachment objects tied to the message."""
        attachment_ids = await self.db.fetch("""
        SELECT id
        FROM attachments
        WHERE message_id = $1
        """, message_id)

        attachment_ids = [r['id'] for r in attachment_ids]

        res = []

        for attachment_id in attachment_ids:
            row = await self.db.fetchrow("""
            SELECT id::text, message_id, channel_id,
                   filename, filesize, image, height, width
            FROM attachments
            WHERE id = $1
            """, attachment_id)

            drow = dict(row)

            drow.pop('message_id')
            drow.pop('channel_id')

            drow['size'] = drow['filesize']
            drow.pop('size')

            # construct attachment url
            proto = 'https' if self.app.config['IS_SSL'] else 'http'
            main_url = self.app.config['MAIN_URL']

            drow['url'] = (f'{proto}://{main_url}/attachments/'
                           f'{row["channel_id"]}/{row["message_id"]}/'
                           f'{row["filename"]}')

            # NOTE: since the url comes from the instance itself
            # i think proxy_url=url is valid.
            drow['proxy_url'] = drow['url']

            res.append(drow)

        return res

    async def _inject_author(self, res: dict):
        """Inject a pseudo-user object when the message is made by a webhook."""
        author_id, webhook_id = res['author_id'], res['webhook_id']

        if author_id is not None:
            res['author'] = await self.get_user(res['author_id'])
            res.pop('webhook_id')
        elif webhook_id is not None:
            res['author'] = {
                'id': webhook_id,
                'username': 'a',
                'avatar': None
            }

        res.pop('author_id')

    async def get_message(self, message_id: int,
                          user_id: Optional[int] = None) -> Optional[Dict]:
        """Get a single message's payload."""
        row = await self.fetchrow_with_json("""
        SELECT id::text, channel_id::text, author_id, webhook_id, content,
            created_at AS timestamp, edited_at AS edited_timestamp,
            tts, mention_everyone, nonce, message_type, embeds
        FROM messages
        WHERE id = $1
        """, message_id)

        if not row:
            return None

        res = dict(row)
        res['nonce'] = str(res['nonce'])
        res['timestamp'] = timestamp_(res['timestamp'])
        res['edited_timestamp'] = timestamp_(res['edited_timestamp'])

        res['type'] = res['message_type']
        res.pop('message_type')

        if res['content'] is None:
            res['content'] = ""

        channel_id = int(row['channel_id'])
        content = row['content']
        guild_id = await self.guild_from_channel(channel_id)

        # calculate user mentions and role mentions by regex
        async def _get_member(user_id):
            user = await self.get_user(user_id)
            member = None

            if guild_id:
                # TODO: maybe make this partial?
                member = await self.get_member_data_one(guild_id, user_id)

            return {**user, **{'member': member}} if member else user

        res['mentions'] = await self._msg_regex(USER_MENTION, _get_member,
                                                row['content'])

        # _dummy just returns the string of the id, since we don't
        # actually use the role objects in mention_roles, just their ids.
        async def _get_role_mention(role_id: int):
            if not guild_id:
                return str(role_id)

            if role_id == guild_id:
                return str(role_id)

            role = await self.get_role(role_id, guild_id)
            if not role:
                return

            if not role['mentionable']:
                return

            return str(role_id)

        res['mention_roles'] = await self._msg_regex(
            ROLE_MENTION, _get_role_mention, content)

        res['reactions'] = await self.get_reactions(message_id, user_id)

        await self._inject_author(res)

        res['attachments'] = await self.get_attachments(message_id)

        # if message is not from a dm, guild_id is None and so, _member_basic
        # will just return None
        res['member'] = await self._member_basic_with_roles(guild_id, user_id)

        if res['member'] is None:
            res.pop('member')

        pin_id = await self.db.fetchval("""
        SELECT message_id
        FROM channel_pins
        WHERE channel_id = $1 AND message_id = $2
        """, channel_id, message_id)

        res['pinned'] = pin_id is not None

        # this is specifically for lazy guilds:
        # only insert when the channel
        # is actually from a guild.
        if guild_id:
            res['guild_id'] = str(guild_id)

        return res

    async def get_invite(self, invite_code: str) -> Optional[Dict]:
        """Fetch invite information given its code."""
        invite = await self.db.fetchrow("""
        SELECT code, guild_id, channel_id
        FROM invites
        WHERE code = $1
        """, invite_code)

        if invite is None:
            return None

        dinv = dict_(invite)

        # fetch some guild info
        guild = await self.db.fetchrow("""
        SELECT id::text, name, splash, icon, verification_level
        FROM guilds
        WHERE id = $1
        """, invite['guild_id'])

        if guild:
            dinv['guild'] = dict(guild)
        else:
            dinv['guild'] = {}

        chan = await self.get_channel(invite['channel_id'])

        if chan is None:
            return None

        dinv['channel'] = {
            'id': chan['id'],
            'name': chan['name'],
            'type': chan['type'],
        }

        dinv.pop('guild_id')
        dinv.pop('channel_id')

        return dinv

    async def get_invite_extra(self, invite_code: str) -> dict:
        """Extra information about the invite, such as
        approximate guild and presence counts."""
        guild_id = await self.db.fetchval("""
        SELECT guild_id
        FROM invites
        WHERE code = $1
        """, invite_code)

        if guild_id is None:
            return {}

        mids = await self.get_member_ids(guild_id)
        pres = await self.presence.guild_presences(mids, guild_id)
        online_count = sum(1 for p in pres if p['status'] == 'online')

        return {
            'approximate_presence_count': online_count,
            'approximate_member_count': len(mids),
        }

    async def get_invite_metadata(self,
                                  invite_code: str) -> Optional[Dict[str, Any]]:
        """Fetch invite metadata (max_age and friends)."""
        invite = await self.db.fetchrow("""
        SELECT code, inviter, created_at, uses,
               max_uses, max_age, temporary, created_at, revoked
        FROM invites
        WHERE code = $1
        """, invite_code)

        if invite is None:
            return None

        dinv = dict_(invite)
        inviter = await self.get_user(invite['inviter'])
        dinv['inviter'] = inviter

        return dinv

    async def get_dm(self, dm_id: int, user_id: int = None) -> Optional[Dict]:
        """Get a DM channel."""
        dm_chan = await self.get_channel(dm_id)

        if user_id and dm_chan:
            dm_chan['recipients'] = _filter_recipients(
                dm_chan['recipients'], str(user_id)
            )

        return dm_chan

    async def guild_from_channel(self, channel_id: int) -> int:
        """Get the guild id coming from a channel id."""
        return await self.db.fetchval("""
        SELECT guild_id
        FROM guild_channels
        WHERE id = $1
        """, channel_id)

    async def get_dm_peer(self, channel_id: int, user_id: int) -> int:
        """Get the peer id on a dm"""
        parties = await self.db.fetchrow("""
        SELECT party1_id, party2_id
        FROM dm_channels
        WHERE id = $1 AND (party1_id = $2 OR party2_id = $2)
        """, channel_id, user_id)

        parties = [parties['party1_id'], parties['party2_id']]

        # get the id of the other party
        parties.remove(user_id)

        return parties[0]

    async def get_emoji(self, emoji_id: int) -> Optional[Dict[str, Any]]:
        """Get a single emoji."""
        row = await self.db.fetchrow("""
        SELECT id::text, name, animated, managed,
               require_colons, uploader_id
        FROM guild_emoji
        WHERE id = $1
        """, emoji_id)

        if not row:
            return None

        drow = dict(row)

        # ????
        drow['roles'] = []

        uploader_id = drow.pop('uploader_id')
        drow['user'] = await self.get_user(uploader_id)

        return drow

    async def get_guild_emojis(self, guild_id: int):
        """Get a list of all emoji objects in a guild."""
        rows = await self.db.fetch("""
        SELECT id
        FROM guild_emoji
        WHERE guild_id = $1
        """, guild_id)

        emoji_ids = [r['id'] for r in rows]

        res = []

        for emoji_id in emoji_ids:
            emoji = await self.get_emoji(emoji_id)
            res.append(emoji)

        return res

    async def get_role_members(self, role_id: int) -> List[int]:
        """Get all members with a role."""
        rows = await self.db.fetch("""
        SELECT user_id
        FROM member_roles
        WHERE role_id = $1
        """, role_id)

        return [r['id'] for r in rows]

    async def all_voice_regions(self) -> List[Dict[str, Any]]:
        """Return a list of all voice regions."""
        rows = await self.db.fetch("""
        SELECT id, name, vip, deprecated, custom
        FROM voice_regions
        """)

        return list(map(dict, rows))

    async def has_feature(self, guild_id: int, feature: str) -> bool:
        """Return if a certain guild has a certain feature."""
        features = await self.db.fetchval("""
        SELECT features FROM guilds
        WHERE id = $1
        """, guild_id)

        return feature.upper() in features
