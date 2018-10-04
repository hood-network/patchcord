import json
from typing import List, Dict, Any

from logbook import Logger

from .enums import ChannelType, RelationshipType
from .schemas import USER_MENTION, ROLE_MENTION


log = Logger(__name__)


async def _dummy(any_id):
    return str(any_id)


def dict_(val):
    return dict(val) if val else None


async def _set_json(con):
    """Set JSON and JSONB codecs for an
    asyncpg connection."""
    await con.set_type_codec(
        'json',
        encoder=json.dumps,
        decoder=json.loads,
        schema='pg_catalog'
    )

    await con.set_type_codec(
        'jsonb',
        encoder=json.dumps,
        decoder=json.loads,
        schema='pg_catalog'
    )


def _filter_recipients(recipients: List[Dict[str, Any]], user_id: int):
    """Filter recipients in a list of recipients, removing
    the one that is reundant (ourselves)."""
    user_id = str(user_id)

    return filter(
        lambda recipient: recipient['id'] != user_id,
        recipients)


class Storage:
    """Class for common SQL statements."""
    def __init__(self, db):
        self.db = db
        self.presence = None

    async def _fetchrow_with_json(self, query: str, *args):
        """Fetch a single row with JSON/JSONB support."""
        # the pool by itself doesn't have
        # set_type_codec, so we must set it manually
        # by acquiring the connection
        async with self.db.acquire() as con:
            await _set_json(con)
            return await con.fetchrow(query, *args)

    async def _fetch_with_json(self, query: str, *args):
        """Fetch many rows with JSON/JSONB support."""
        async with self.db.acquire() as con:
            await _set_json(con)
            return await con.fetch(query, *args)

    async def get_user(self, user_id, secure=False) -> Dict[str, Any]:
        """Get a single user payload."""
        user_id = int(user_id)

        # TODO: query less instead of popping when secure=True
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

        # TODO: emojis
        drow['emojis'] = []
        return drow

    async def get_user_guilds(self, user_id: int) -> List[int]:
        """Get all guild IDs a user is on."""
        guild_ids = await self.db.fetch("""
        SELECT guild_id
        FROM members
        WHERE user_id = $1
        """, user_id)

        return [row['guild_id'] for row in guild_ids]

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

        members = await self.get_member_multi(guild_id, mids)
        return members

    async def _chan_last_message(self, channel_id: int):
        return await self.db.fetch("""
        SELECT MAX(id)
        FROM messages
        WHERE channel_id = $1
        """, channel_id)

    async def _channels_extra(self, row) -> Dict:
        """Fill in more information about a channel."""
        channel_type = row['type']

        chan_type = ChannelType(channel_type)

        if chan_type == ChannelType.GUILD_TEXT:
            topic = await self.db.fetchval("""
            SELECT topic FROM guild_text_channels
            WHERE id = $1
            """, row['id'])

            return {**row, **{
                'topic': topic,
                'last_message_id': str(
                    await self._chan_last_message(row['id']))
            }}
        elif chan_type == ChannelType.GUILD_VOICE:
            vrow = await self.db.fetchval("""
            SELECT bitrate, user_limit FROM guild_voice_channels
            WHERE id = $1
            """, row['id'])

            return {**row, **dict(vrow)}

        log.warning('unknown channel type: {}', chan_type)

    async def get_chan_type(self, channel_id: int) -> int:
        """Get the channel type integer, given channel ID."""
        return await self.db.fetchval("""
        SELECT channel_type
        FROM channels
        WHERE channels.id = $1
        """, channel_id)

    async def _chan_overwrites(self, channel_id):
        overwrite_rows = await self.db.fetch("""
        SELECT target_type, target_role, target_user, allow, deny
        FROM channel_overwrites
        WHERE channel_id = $1
        """, channel_id)

        def _overwrite_convert(row):
            drow = dict(row)
            drow['type'] = drow['target_type']

            # if type is 0, the overwrite is for a user
            # if type is 1, the overwrite is for a role
            drow['id'] = {
                0: drow['target_user'],
                1: drow['target_role'],
            }[drow['type']]

            drow['id'] = str(drow['id'])

            drow.pop('overwrite_type')
            drow.pop('target_user')
            drow.pop('target_role')

            return drow

        return list(map(_overwrite_convert, overwrite_rows))

    async def get_channel(self, channel_id: int) -> Dict[str, Any]:
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
            res['permission_overwrites'] = \
                list(await self._chan_overwrites(channel_id))

            res['id'] = str(res['id'])
            return res
        elif ctype == ChannelType.DM:
            dm_row = await self.db.fetchrow("""
            SELECT party1_id, party2_id
            FROM dm_channels
            WHERE id = $1
            """, channel_id)

            drow = dict(dm_row)
            drow['type'] = chan_type

            drow['last_message_id'] = str(
                await self._chan_last_message(channel_id))

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
            pass

        return None

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

            drow = dict(row)
            drow['type'] = ctype

            res = await self._channels_extra(drow)

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

        mids = [int(m['user']['id']) for m in members]

        return {**res, **{
            'member_count': member_count,
            'members': members,
            'voice_states': [],
            'channels': channels,
            'roles': roles,

            'presences': await self.presence.guild_presences(
                mids, guild_id
            ),
        }}

    async def get_guild_full(self, guild_id: int,
                             user_id: int, large_count: int = 250) -> Dict:
        guild = await self.get_guild(guild_id, user_id)
        extra = await self.get_guild_extra(guild_id, user_id, large_count)

        return {**guild, **extra}

    async def guild_exists(self, guild_id: int):
        """Return if a given guild ID exists."""
        owner_id = await self.db.fetch("""
        SELECT owner_id
        FROM guilds
        WHERE id = $1
        """, guild_id)

        return owner_id is not None

    async def get_member_ids(self, guild_id: int) -> List[int]:
        rows = await self.db.fetch("""
        SELECT user_id
        FROM members
        WHERE guild_id = $1
        """, guild_id)

        return [r[0] for r in rows]

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

        # this is specifically for lazy guilds.
        guild_id = await self.db.fetchval("""
        SELECT guild_id
        FROM guild_channels
        WHERE guild_channels.id = $1
        """, int(res['channel_id']))

        # only insert when the channel
        # is actually from a guild.
        if guild_id:
            res['guild_id'] = guild_id

        return res

    async def fetch_notes(self, user_id: int) -> dict:
        """Fetch a users' notes"""
        note_rows = await self.db.fetch("""
        SELECT target_id, note
        FROM notes
        WHERE user_id = $1
        """, user_id)

        return {str(row['target_id']): row['note']
                for row in note_rows}

    async def get_invite(self, invite_code: str) -> dict:
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

        dinv['guild'] = dict(guild)

        # TODO: query actual guild features
        dinv['guild']['features'] = []

        chan = await self.get_channel(invite['channel_id'])
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

    async def get_invite_metadata(self, invite_code: str) -> Dict[str, Any]:
        """Fetch invite metadata (max_age and friends)."""
        invite = await self.db.fetchrow("""
        SELECT code, inviter, created_at, uses,
               max_uses, max_age, temporary, created_at, revoked
        FROM invites
        WHERE code = $1
        """, invite_code)

        if invite is None:
            return

        dinv = dict_(invite)
        inviter = await self.get_user(invite['inviter'])
        dinv['inviter'] = inviter

        return dinv

    async def get_user_settings(self, user_id: int) -> Dict[str, Any]:
        """Get current user settings."""
        row = await self._fetchrow_with_json("""
        SELECT *
        FROM user_settings
        WHERE id = $1
        """, user_id)

        if not row:
            log.info('Generating user settings for {}', user_id)

            await self.db.execute("""
            INSERT INTO user_settings (id)
            VALUES ($1)
            """, user_id)

            # recalling get_user_settings
            # should work after adding
            return await self.get_user_settings(user_id)

        drow = dict(row)
        drow.pop('id')
        return drow

    async def get_relationships(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all relationships for a user."""
        # first, fetch all friendships outgoing
        # from the user
        _friend = RelationshipType.FRIEND.value
        _block = RelationshipType.BLOCK.value
        _incoming = RelationshipType.INCOMING.value
        _outgoing = RelationshipType.OUTGOING.value

        # check all outgoing friends
        friends = await self.db.fetch("""
        SELECT user_id, peer_id, rel_type
        FROM relationships
        WHERE user_id = $1 AND rel_type = $2
        """, user_id, _friend)
        friends = list(map(dict, friends))

        # mutuals is a list of ints
        # of people who are actually friends
        # and accepted the friend request
        mutuals = []

        # for each outgoing, find if theres an outgoing from them
        for row in friends:
            is_friend = await self.db.fetchrow(
                """
                SELECT user_id, peer_id
                FROM relationships
                WHERE user_id = $1 AND peer_id = $2 AND rel_type = $3
                """, row['peer_id'], row['user_id'],
                _friend)

            if is_friend is not None:
                mutuals.append(row['peer_id'])

        # fetch friend requests directed at us
        incoming_friends = await self.db.fetch("""
        SELECT user_id, peer_id
        FROM relationships
        WHERE peer_id = $1 AND rel_type = $2
        """, user_id, _friend)

        # only need their ids
        incoming_friends = [r['user_id'] for r in incoming_friends
                            if r['user_id'] not in mutuals]

        # only fetch blocks we did,
        # not fetching the ones people did to us
        blocks = await self.db.fetch("""
        SELECT user_id, peer_id
        FROM relationships
        WHERE user_id = $1 AND rel_type = $2
        """, user_id, _block)
        blocks = list(map(dict, blocks))

        res = []

        for drow in friends:
            drow['type'] = drow['rel_type']
            drow.pop('rel_type')

            # check if the receiver is a mutual
            # if it isnt, its still on a friend request stage
            if drow['peer_id'] not in mutuals:
                drow['id'] = str(drow['peer_id'])
                drow['type'] = _outgoing

            drow['user'] = await self.get_user(drow['peer_id'])

            drow.pop('user_id')
            drow.pop('peer_id')
            res.append(drow)

        for peer_id in incoming_friends:
            res.append({
                'id': str(peer_id),
                'user': await self.get_user(peer_id),
                'type': _incoming,
            })

        for drow in blocks:
            drow['type'] = drow['rel_type']
            drow.pop('rel_type')

            drow['id'] = str(drow['peer_id'])
            drow['user'] = await self.get_user(drow['peer_id'])

            drow.pop('user_id')
            drow.pop('peer_id')
            res.append(drow)

        return res

    async def get_dm(self, dm_id: int, user_id: int = None):
        dm_chan = await self.get_channel(dm_id)

        if user_id:
            dm_chan['recipients'] = _filter_recipients(
                dm_chan['recipients'], user_id
            )

        return dm_chan

    async def get_dms(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all DM channels for a user, including group DMs.

        This will only fetch channels the user has in their state,
        which is different than the whole list of DM channels.
        """
        dm_ids = await self.db.fetch("""
        SELECT id
        FROM dm_channel_state
        WHERE user_id = $1
        """, user_id)

        res = []

        for dm_id in dm_ids:
            dm_chan = await self.get_dm(dm_id, user_id)
            res.append(dm_chan)

        return res

    async def get_all_dms(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all DMs for a user, regardless of the DM state."""
        dm_ids = await self.db.fetch("""
        SELECT id
        FROM dm_channels
        WHERE party1_id = $1 OR party2_id = $2
        """, user_id)

        res = []

        for dm_id in dm_ids:
            dm_chan = await self.get_dm(dm_id, user_id)
            res.append(dm_chan)

        return res
