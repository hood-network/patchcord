from typing import List, Dict, Any

from logbook import Logger
from litecord.enums import RelationshipType

log = Logger(__name__)


class UserStorage:
    """Storage functions related to a single user."""
    def __init__(self, storage):
        self.storage = storage
        self.db = storage.db

    async def fetch_notes(self, user_id: int) -> dict:
        """Fetch a users' notes"""
        note_rows = await self.db.fetch("""
        SELECT target_id, note
        FROM notes
        WHERE user_id = $1
        """, user_id)

        return {str(row['target_id']): row['note']
                for row in note_rows}

    async def get_user_settings(self, user_id: int) -> Dict[str, Any]:
        """Get current user settings."""
        row = await self.storage.fetchrow_with_json("""
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

            drow['user'] = await self.storage.get_user(drow['peer_id'])

            drow.pop('user_id')
            drow.pop('peer_id')
            res.append(drow)

        for peer_id in incoming_friends:
            res.append({
                'id': str(peer_id),
                'user': await self.storage.get_user(peer_id),
                'type': _incoming,
            })

        for drow in blocks:
            drow['type'] = drow['rel_type']
            drow.pop('rel_type')

            drow['id'] = str(drow['peer_id'])
            drow['user'] = await self.storage.get_user(drow['peer_id'])

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
            dm_chan = await self.storage.get_dm(dm_id, user_id)
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
