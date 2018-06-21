from typing import List, Dict, Any

from .enums import ChannelType


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
            duser.pop('mfa_enabled')
            duser.pop('verified')
            duser.pop('mfa_enabled')

        return duser

    async def get_guild(self, guild_id: int, state=None) -> Dict:
        """Get gulid payload."""
        row = await self.db.fetchrow("""
        SELECT *
        FROM guilds
        WHERE guilds.id = $1
        """, guild_id)

        if not row:
            return

        drow = dict(row)

        if state:
            drow['owner'] = drow['owner_id'] == state.user_id

        # TODO: Probably a really bad idea to repeat str() calls
        #   Any ideas to make this simpler?
        #   (No, changing the types on the db wouldn't be nice)
        drow['id'] = str(drow['id'])
        drow['owner_id'] = str(drow['owner_id'])
        drow['afk_channel_id'] = str(drow['afk_channel_id'])
        drow['embed_channel_id'] = str(drow['embed_channel_id'])
        drow['widget_channel_id'] = str(drow['widget_channel_id'])
        drow['system_channel_id'] = str(drow['system_channel_id'])

        return {**drow, **{
            'roles': [],
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

    async def get_member_data(self, guild_id) -> List[Dict[str, Any]]:
        """Get member information on a guild."""
        members_basic = await self.db.fetch("""
        SELECT user_id, nickname, joined_at
        FROM members
        WHERE guild_id = $1
        """, guild_id)

        members = []

        for row in members_basic:
            member_id = row['user_id']

            members_roles = await self.db.fetch("""
            SELECT role_id::text
            FROM member_roles
            WHERE guild_id = $1 AND user_id = $2
            """, guild_id, member_id)

            members.append({
                'user': await self.get_user(member_id),
                'nick': row['nickname'],
                'roles': [row[0] for row in members_roles],
                'joined_at': row['joined_at'].isoformat(),
                'deaf': row['deafened'],
                'mute': row['muted'],
            })

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

    async def get_channel_data(self, guild_id) -> List[Dict]:
        """Get channel information on a guild"""
        channel_basics = await self.db.fetch("""
        SELECT * FROM guild_channels
        WHERE guild_id = $1
        """, guild_id)

        channels = []

        for row in channel_basics:
            ctype = await self.db.fetchval("""
            SELECT channel_type FROM channels
            WHERE id = $1
            """, row['id'])

            res = await self._channels_extra(row, ctype)

            # type is a SQL keyword, so we can't do
            # 'overwrite_type AS type'
            overwrite_rows = await self.db.fetch("""
            SELECT user_id::text AS id, overwrite_type, allow, deny
            FROM channel_overwrites
            WHERE channel_id = $1
            """, row['id'])

            def _overwrite_convert(ov_row):
                drow = dict(ov_row)
                drow['type'] = drow['overwrite_type']
                drow.pop('overwrite_type')
                return drow

            res['permission_overwrites'] = list(map(_overwrite_convert,
                                                    overwrite_rows))

            # Making sure.
            res['id'] = str(res['id'])
            channels.append(res)

        return channels

    async def get_guild_extra(self, guild_id: int, state=None) -> Dict:
        """Get extra information about a guild."""
        res = {}

        member_count = await self.db.fetchval("""
        SELECT COUNT(*)
        FROM members
        WHERE guild_id = $1
        """, guild_id)

        if state:
            joined_at = await self.db.fetchval("""
            SELECT joined_at
            FROM members
            WHERE guild_id = $1 AND user_id = $2
            """, guild_id, state.user_id)

            res['large'] = state.large > member_count
            res['joined_at'] = joined_at.isoformat()

        members = await self.get_member_data(guild_id)
        channels = await self.get_channel_data(guild_id)

        return {**res, **{
            'member_count': member_count,
            'members': members,
            'voice_states': [],
            'channels': channels,
            # TODO: finish those
            'presences': [],
        }}
