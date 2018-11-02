import json
from typing import List, Dict, Any

from logbook import Logger

from .enums import ChannelType, RelationshipType
from .schemas import USER_MENTION, ROLE_MENTION


log = Logger(__name__)


async def _dummy(any_id):
    return str(any_id)


def maybe(typ, val):
    return typ(val) if val is not None else None


def dict_(val):
    return maybe(dict, val)


def str_(val):
    return maybe(str, val)


def timestamp_(dt):
    return dt.isoformat() if dt else None


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

    return list(filter(
        lambda recipient: recipient['id'] != user_id,
        recipients))


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
            flags, bot, mfa_enabled, verified, premium_since
        FROM users
        WHERE users.id = $1
        """, user_id)

        if not user_row:
            return

        duser = dict(user_row)

        duser['premium'] = duser['premium_since'] is not None
        duser.pop('premium_since')

        if not secure:
            duser.pop('email')
            duser.pop('verified')
            duser.pop('mfa_enabled')
        else:
            duser['mobile'] = False
            duser['phone'] = None

        return duser

    async def search_user(self, username: str, discriminator: str) -> int:
        """Search a user"""
        if len(discriminator) < 4:
            # how do we do this in f-strings again..?
            discriminator = '%04d' % discriminator

        return await self.db.fetchval("""
        SELECT id FROM users
        WHERE username = $1 AND discriminator = $2
        """, username, discriminator)

    async def get_guild(self, guild_id: int, user_id=None) -> Dict:
        """Get gulid payload."""
        row = await self.db.fetchrow("""
        SELECT id::text, owner_id::text, name, icon, splash,
               region, afk_channel_id::text, afk_timeout,
               verification_level, default_message_notifications,
               explicit_content_filter, mfa_level,
               embed_enabled, embed_channel_id::text,
               widget_enabled, widget_channel_id::text,
               system_channel_id::text
        FROM guilds
        WHERE guilds.id = $1
        """, guild_id)

        if not row:
            return

        drow = dict(row)

        if user_id:
            drow['owner'] = drow['owner_id'] == str(user_id)

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

    async def _member_basic(self, guild_id: int, member_id: int):
        return await self.db.fetchrow("""
        SELECT user_id, nickname, joined_at, deafened, muted
        FROM members
        WHERE guild_id = $1 and user_id = $2
        """, guild_id, member_id)

    async def _member_dict(self, row, guild_id, member_id) -> Dict[str, Any]:
        roles = await self.db.fetch("""
        SELECT role_id::text
        FROM member_roles
        WHERE guild_id = $1 AND user_id = $2
        """, guild_id, member_id)

        return {
            'user': await self.get_user(member_id),
            'nick': row['nickname'],

            # we don't send the @everyone role's id to
            # the user since it is known that everyone has
            # that role.
            'roles': [r['role_id'] for r in roles],
            'joined_at': row['joined_at'].isoformat(),
            'deaf': row['deafened'],
            'mute': row['muted'],
        }

    async def get_member_data_one(self, guild_id: int,
                                  member_id: int) -> Dict[str, Any]:
        """Get data about one member in a guild."""
        basic = await self._member_basic(guild_id, member_id)

        if not basic:
            return

        return await self._member_dict(basic, guild_id, member_id)

    async def get_member_multi(self, guild_id: int,
                               user_ids: List[int]) -> List[Dict[str, Any]]:
        """Get member information about multiple users in a guild."""
        members = []

        for user_id in user_ids:
            row = await self._member_basic(guild_id, user_id)

            if not row:
                continue

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
            topic = await self.db.fetchval("""
            SELECT topic FROM guild_text_channels
            WHERE id = $1
            """, row['id'])

            last_msg = await self.chan_last_message_str(row['id'])

            return {**row, **{
                'topic': topic,
                'last_message_id': last_msg,
            }}

        if chan_type == ChannelType.GUILD_VOICE:
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

    async def _chan_overwrites(self, channel_id: int) -> List[Dict[str, Any]]:
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
            SELECT id, party1_id, party2_id
            FROM dm_channels
            WHERE id = $1
            """, channel_id)

            drow = dict(dm_row)
            drow['type'] = chan_type

            drow['last_message_id'] = await self.chan_last_message_str(
                channel_id)

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
            # TODO: group dms
            pass

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

            res['permission_overwrites'] = \
                list(await self._chan_overwrites(row['id']))

            # Making sure.
            res['id'] = str(res['id'])
            channels.append(res)

        return channels

    async def get_role(self, role_id: int,
                       guild_id: int = None) -> Dict[str, Any]:
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
            return

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

            res['joined_at'] = joined_at.isoformat()

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

            # TODO: voice state management
            'voice_states': [],
        }}

    async def get_guild_full(self, guild_id: int,
                             user_id: int, large_count: int = 250) -> Dict:
        """Get full information on a guild.

        This is a very expensive operation.
        """
        guild = await self.get_guild(guild_id, user_id)
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
        res['edited_timestamp'] = timestamp_(res['edited_timestamp'])

        res['type'] = res['message_type']
        res.pop('message_type')

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
                # TODO: check MENTION_EVERYONE permission
                return str(role_id)

            role = await self.get_role(role_id, guild_id)
            if not role:
                return

            if not role['mentionable']:
                return

            return str(role_id)

        res['mention_roles'] = await self._msg_regex(
            ROLE_MENTION, _get_role_mention, content)

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

        # this is specifically for lazy guilds:
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
        SELECT user_id, peer_id, rel_type
        FROM relationships
        WHERE user_id = $1 AND rel_type = $2
        """, user_id, _block)
        blocks = list(map(dict, blocks))

        res = []

        for drow in friends:
            drow['type'] = drow['rel_type']
            drow['id'] = str(drow['peer_id'])
            drow.pop('rel_type')

            # check if the receiver is a mutual
            # if it isnt, its still on a friend request stage
            if drow['peer_id'] not in mutuals:
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

    async def get_friend_ids(self, user_id: int) -> List[int]:
        """Get all friend IDs for a user."""
        rels = await self.get_relationships(user_id)

        return [int(r['user']['id'])
                for r in rels
                if r['type'] == RelationshipType.FRIEND.value]

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
        SELECT dm_id
        FROM dm_channel_state
        WHERE user_id = $1
        """, user_id)

        dm_ids = [r['dm_id'] for r in dm_ids]

        res = []

        for dm_id in dm_ids:
            dm_chan = await self.get_dm(dm_id, user_id)
            res.append(dm_chan)

        return res

    async def get_read_state(self, user_id: int) -> List[Dict[str, Any]]:
        """Get the read state for a user."""
        rows = await self.db.fetch("""
        SELECT channel_id, last_message_id, mention_count
        FROM user_read_state
        WHERE user_id = $1
        """, user_id)

        res = []

        for row in rows:
            drow = dict(row)

            drow['id'] = str(drow['channel_id'])
            drow.pop('channel_id')

            drow['last_message_id'] = str(drow['last_message_id'])

            res.append(drow)

        return res

    async def guild_from_channel(self, channel_id: int):
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

    async def get_guild_settings_one(self, user_id: int,
                                     guild_id: int) -> dict:
        """Get guild settings information for a single guild."""
        row = await self.db.fetchrow("""
        SELECT guild_id::text, suppress_everyone, muted,
               message_notifications, mobile_push
        FROM guild_settings
        WHERE user_id = $1 AND guild_id = $2
        """, user_id, guild_id)

        if not row:
            await self.db.execute("""
            INSERT INTO guild_settings (user_id, guild_id)
            VALUES ($1, $2)
            """, user_id, guild_id)

            return await self.get_guild_settings_one(user_id, guild_id)

        gid = int(row['guild_id'])
        drow = dict(row)

        chan_overrides = {}

        overrides = await self.db.fetch("""
        SELECT channel_id::text, muted, message_notifications
        FROM guild_settings_channel_overrides
        WHERE
            user_id = $1
        AND guild_id = $2
        """, user_id, gid)

        for chan_row in overrides:
            dcrow = dict(chan_row)

            chan_id = dcrow['channel_id']
            dcrow.pop('channel_id')

            chan_overrides[chan_id] = dcrow

        return {**drow, **{
            'channel_overrides': chan_overrides
        }}

    async def get_guild_settings(self, user_id: int):
        """Get the specific User Guild Settings,
        for all guilds a user is on."""

        res = []

        settings = await self.db.fetch("""
        SELECT guild_id::text, suppress_everyone, muted,
               message_notifications, mobile_push
        FROM guild_settings
        WHERE user_id = $1
        """, user_id)

        for row in settings:
            gid = int(row['guild_id'])
            drow = dict(row)

            chan_overrides = {}

            overrides = await self.db.fetch("""
            SELECT channel_id::text, muted, message_notifications
            FROM guild_settings_channel_overrides
            WHERE
                user_id = $1
            AND guild_id = $2
            """, user_id, gid)

            for chan_row in overrides:
                dcrow = dict(chan_row)

                # channel_id isn't on the value of the dict
                # so we query it (for the key) then pop
                # from the value
                chan_id = dcrow['channel_id']
                dcrow.pop('channel_id')

                chan_overrides[chan_id] = dcrow

            res.append({**drow, **{
                'channel_overrides': chan_overrides
            }})

        return res

