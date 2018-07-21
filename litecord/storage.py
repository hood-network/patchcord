from typing import List, Dict, Any

from .enums import ChannelType
from .schemas import USER_MENTION, ROLE_MENTION


async def _dummy(any_id):
    return str(any_id)


class Storage:
    """Class for common SQL statements."""
    def __init__(self, db):
        self.db = db

    async def get_user(self, user_id, secure=False) -> Dict[str, Any]:
        """Get a single user payload."""
        user_id = int(user_id)

        user_row = await self.db.fetchrow("""
        SELECT id::text, username, discriminator, avatar, email,
            flags, bot, mfa_enabled, verified, premium
        FROM users
        WHERE users.id = $1
        """, user_id)

        if not user_row:
            return

        duser = dict(user_row)

        if not secure:
            duser.pop('email')
            duser.pop('verified')
            duser.pop('mfa_enabled')

        return duser

    async def get_guild(self, guild_id: int, user_id=None) -> Dict:
        """Get gulid payload."""
        row = await self.db.fetchrow("""
        SELECT *
        FROM guilds
        WHERE guilds.id = $1
        """, guild_id)

        if not row:
            return

        drow = dict(row)

        if user_id:
            drow['owner'] = drow['owner_id'] == user_id

        # TODO: Probably a really bad idea to repeat str() calls
        #   Any ideas to make this simpler?
        #   (No, changing the types on the db wouldn't be nice)
        drow['id'] = str(drow['id'])
        drow['owner_id'] = str(drow['owner_id'])
        drow['afk_channel_id'] = str(drow['afk_channel_id']) \
            if drow['afk_channel_id'] else None
        drow['embed_channel_id'] = str(drow['embed_channel_id']) \
            if drow['embed_channel_id'] else None

        drow['widget_channel_id'] = str(drow['widget_channel_id']) \
            if drow['widget_channel_id'] else None
        drow['system_channel_id'] = str(drow['system_channel_id']) \
            if drow['system_channel_id'] else None

        return {**drow, **{
            # TODO: those
            'emojis': [],
        }}

    async def get_user_guilds(self, user_id: int) -> List[int]:
        """Get all guild IDs a user is on."""
        guild_ids = await self.db.fetch("""
        SELECT guild_id
        FROM members
        WHERE user_id = $1
        """, user_id)

        return guild_ids

    async def get_member_data_one(self, guild_id, member_id) -> Dict[str, any]:
        basic = await self.db.fetchrow("""
        SELECT user_id, nickname, joined_at, deafened, muted
        FROM members
        WHERE guild_id = $1 and user_id = $2
        """, guild_id, member_id)

        if not basic:
            return

        members_roles = await self.db.fetch("""
        SELECT role_id::text
        FROM member_roles
        WHERE guild_id = $1 AND user_id = $2
        """, guild_id, member_id)

        return {
            'user': await self.get_user(member_id),
            'nick': basic['nickname'],
            'roles': [row[0] for row in members_roles],
            'joined_at': basic['joined_at'].isoformat(),
            'deaf': basic['deafened'],
            'mute': basic['muted'],
        }

    async def _member_dict(self, row, guild_id, member_id) -> Dict[str, Any]:
        members_roles = await self.db.fetch("""
        SELECT role_id::text
        FROM member_roles
        WHERE guild_id = $1 AND user_id = $2
        """, guild_id, member_id)

        return {
            'user': await self.get_user(member_id),
            'nick': row['nickname'],
            'roles': [guild_id] + [row[0] for row in members_roles],
            'joined_at': row['joined_at'].isoformat(),
            'deaf': row['deafened'],
            'mute': row['muted'],
        }

    async def get_member_multi(self, guild_id: int,
                               user_ids: List[int]) -> List[Dict[str, Any]]:
        """Get member information about multiple users in a guild."""
        members = []

        # bad idea bad idea bad idea
        for user_id in user_ids:
            row = await self.db.fetchrow("""
            SELECT user_id, nickname, joined_at, defened, muted
            FROM members
            WHERE guild_id = $1 AND user_id = $2
            """, guild_id, user_id)

            member = await self._member_dict(row, guild_id, user_id)
            members.append(member)

        return members

    async def get_member_data(self, guild_id: int) -> List[Dict[str, Any]]:
        """Get member information on a guild."""
        members_basic = await self.db.fetch("""
        SELECT user_id, nickname, joined_at, deafened, muted
        FROM members
        WHERE guild_id = $1
        """, guild_id)

        members = []

        for row in members_basic:
            member = await self._member_dict(row, guild_id, row['user_id'])
            members.append(member)

        return members

    async def _channels_extra(self, row, channel_type: int) -> Dict:
        """Fill in more information about a channel."""
        # TODO: This could probably be better with a dictionary.

        # TODO: dm and group dm?
        if channel_type == ChannelType.GUILD_TEXT:
            topic = await self.db.fetchval("""
            SELECT topic FROM guild_text_channels
            WHERE id = $1
            """, row['id'])

            return {**row, **{
                'topic': topic,
            }}
        elif channel_type == ChannelType.GUILD_VOICE:
            vrow = await self.db.fetchval("""
            SELECT bitrate, user_limit FROM guild_voice_channels
            WHERE id = $1
            """, row['id'])

            return {**row, **dict(vrow)}

    async def get_chan_type(self, channel_id) -> int:
        return await self.db.fetchval("""
        SELECT channel_type
        FROM channels
        WHERE channels.id = $1
        """, channel_id)

    async def _chan_overwrites(self, channel_id):
        overwrite_rows = await self.db.fetch("""
        SELECT target_id::text AS id, overwrite_type, allow, deny
        FROM channel_overwrites
        WHERE channel_id = $1
        """, channel_id)

        def _overwrite_convert(ov_row):
            drow = dict(ov_row)
            drow['type'] = drow['overwrite_type']
            drow.pop('overwrite_type')
            return drow

        return map(_overwrite_convert, overwrite_rows)

    async def get_channel(self, channel_id) -> Dict[str, Any]:
        """Fetch a single channel's information."""
        chan_type = await self.get_chan_type(channel_id)

        if chan_type in (ChannelType.GUILD_TEXT, ChannelType.GUILD_VOICE,
                         ChannelType.GUILD_CATEGORY):
            base = await self.db.fetchrow("""
            SELECT id, guild_id::text, parent_id, name, position, nsfw
            FROM guild_channels
            WHERE guild_channels.id = $1
            """, channel_id)

            res = await self._channels_extra(dict(base), chan_type)
            res['type'] = chan_type
            res['permission_overwrites'] = \
                list(await self._chan_overwrites(channel_id))

            res['id'] = str(res['id'])
            return res
        else:
            # TODO: dms and group dms
            pass

    async def get_channel_data(self, guild_id) -> List[Dict]:
        """Get channel information on a guild"""
        channel_basics = await self.db.fetch("""
        SELECT id, guild_id::text, parent_id, name, position, nsfw
        FROM guild_channels
        WHERE guild_id = $1
        """, guild_id)

        channels = []

        for row in channel_basics:
            ctype = await self.db.fetchval("""
            SELECT channel_type FROM channels
            WHERE id = $1
            """, row['id'])

            res = await self._channels_extra(dict(row), ctype)
            res['type'] = ctype

            res['permission_overwrites'] = \
                list(await self._chan_overwrites(row['id']))

            # Making sure.
            res['id'] = str(res['id'])
            channels.append(res)

        return channels

    async def get_role_data(self, guild_id: int) -> List[Dict[str, Any]]:
        roledata = await self.db.fetch("""
        SELECT id::text, name, color, hoist, position,
               permissions, managed, mentionable
        FROM roles
        WHERE guild_id = $1
        """, guild_id)

        roles = []

        for row in roledata:
            roles.append(dict(row))

        return roles

    async def get_guild_extra(self, guild_id: int,
                              user_id=None, large=None) -> Dict:
        """Get extra information about a guild."""
        res = {}

        member_count = await self.db.fetchval("""
        SELECT COUNT(*)
        FROM members
        WHERE guild_id = $1
        """, guild_id)

        if user_id and large:
            joined_at = await self.db.fetchval("""
            SELECT joined_at
            FROM members
            WHERE guild_id = $1 AND user_id = $2
            """, guild_id, user_id)

            res['large'] = member_count > large
            res['joined_at'] = joined_at.isoformat()

        members = await self.get_member_data(guild_id)
        channels = await self.get_channel_data(guild_id)
        roles = await self.get_role_data(guild_id)

        return {**res, **{
            'member_count': member_count,
            'members': members,
            'voice_states': [],
            'channels': channels,
            'roles': roles,

            # TODO: finish presences
            'presences': [],
        }}

    async def _msg_regex(self, regex, method, content) -> List[Dict]:
        res = []

        for match in regex.finditer(content):
            found_id = match.group(1)

            try:
                found_id = int(found_id)
            except ValueError:
                continue

            obj = await method(found_id)
            if obj:
                res.append(obj)

        return res

    async def get_message(self, message_id: int) -> Dict:
        """Get a single message's payload."""
        row = await self.db.fetchrow("""
        SELECT id::text, channel_id::text, author_id, content,
            created_at AS timestamp, edited_at AS edited_timestamp,
            tts, mention_everyone, nonce, message_type
        FROM messages
        WHERE id = $1
        """, message_id)

        if not row:
            return

        res = dict(row)
        res['nonce'] = str(res['nonce'])
        res['timestamp'] = res['timestamp'].isoformat()
        res['type'] = res['message_type']
        res.pop('message_type')

        # calculate user mentions and role mentions by regex
        res['mentions'] = await self._msg_regex(USER_MENTION, self.get_user,
                                                row['content'])

        # _dummy just returns the string of the id, since we don't
        # actually use the role objects in mention_roles, just their ids.
        res['mention_roles'] = await self._msg_regex(ROLE_MENTION, _dummy,
                                                     row['content'])

        # TODO: handle webhook authors
        res['author'] = await self.get_user(res['author_id'])
        res.pop('author_id')

        # TODO: res['attachments']
        res['attachments'] = []

        # TODO: res['embeds']
        res['embeds'] = []

        # TODO: res['reactions']
        res['reactions'] = []

        # TODO: res['pinned']
        res['pinned'] = False

        return res
