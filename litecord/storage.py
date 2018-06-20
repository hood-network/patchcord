from typing import Dict


class Storage:
    """Class for common SQL statements."""
    def __init__(self, db):
        self.db = db

    async def get_user(self, guild_id, secure=False):
        pass

    async def get_guild(self, guild_id: int, state) -> Dict:
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

        members_basic = await self.db.fetch("""
        SELECT user_id, nickname, joined_at
        FROM members
        WHERE guild_id = $1
        """, guild_id)

        members = []

        for row in members_basic:
            member_id = row['user_id']

            members_roles = await self.db.fetch("""
            SELECT role_id
            FROM member_roles
            WHERE guild_id = $1 AND user_id = $2
            """, guild_id, member_id)

            members.append({
                'user': await self.get_user(member_id),
                'nick': row['nickname'],
                'roles': [str(row[0]) for row in members_roles],
                'joined_at': row['joined_at'].isoformat(),
                'deaf': row['deafened'],
                'mute': row['muted'],
            })

        return {**res, **{
            'member_count': member_count,
            'members': members,
            'voice_states': [],
            # TODO: finish those
            'channels': [],
            'presences': [],
        }}
