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
        note_rows = await self.db.fetch(
            """
        SELECT target_id, note
        FROM notes
        WHERE user_id = $1
        """,
            user_id,
        )

        return {str(row["target_id"]): row["note"] for row in note_rows}

    async def get_user_settings(self, user_id: int) -> Dict[str, Any]:
        """Get current user settings."""
        row = await self.storage.fetchrow_with_json(
            """
        SELECT *
        FROM user_settings
        WHERE id = $1
        """,
            user_id,
        )

        if row is None:
            log.info("Generating user settings for {}", user_id)

            await self.db.execute(
                """
            INSERT INTO user_settings (id)
            VALUES ($1)
            """,
                user_id,
            )

            # recalling get_user_settings
            # should work after adding
            return await self.get_user_settings(user_id)

        drow = dict(row)
        drow.pop("id")
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
        friends = await self.db.fetch(
            """
        SELECT user_id, peer_id, rel_type
        FROM relationships
        WHERE user_id = $1 AND rel_type = $2
        """,
            user_id,
            _friend,
        )
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
                """,
                row["peer_id"],
                row["user_id"],
                _friend,
            )

            if is_friend is not None:
                mutuals.append(row["peer_id"])

        # fetch friend requests directed at us
        incoming_friends = await self.db.fetch(
            """
        SELECT user_id, peer_id
        FROM relationships
        WHERE peer_id = $1 AND rel_type = $2
        """,
            user_id,
            _friend,
        )

        # only need their ids
        incoming_friends = [
            r["user_id"] for r in incoming_friends if r["user_id"] not in mutuals
        ]

        # only fetch blocks we did,
        # not fetching the ones people did to us
        blocks = await self.db.fetch(
            """
        SELECT user_id, peer_id, rel_type
        FROM relationships
        WHERE user_id = $1 AND rel_type = $2
        """,
            user_id,
            _block,
        )
        blocks = list(map(dict, blocks))

        res = []

        for drow in friends:
            drow["type"] = drow["rel_type"]
            drow["id"] = str(drow["peer_id"])
            drow.pop("rel_type")

            # check if the receiver is a mutual
            # if it isnt, its still on a friend request stage
            if drow["peer_id"] not in mutuals:
                drow["type"] = _outgoing

            drow["user"] = await self.storage.get_user(drow["peer_id"])

            drow.pop("user_id")
            drow.pop("peer_id")
            res.append(drow)

        for peer_id in incoming_friends:
            res.append(
                {
                    "id": str(peer_id),
                    "user": await self.storage.get_user(peer_id),
                    "type": _incoming,
                }
            )

        for drow in blocks:
            drow["type"] = drow["rel_type"]
            drow.pop("rel_type")

            drow["id"] = str(drow["peer_id"])
            drow["user"] = await self.storage.get_user(drow["peer_id"])

            drow.pop("user_id")
            drow.pop("peer_id")
            res.append(drow)

        return res

    async def get_friend_ids(self, user_id: int) -> List[int]:
        """Get all friend IDs for a user."""
        rels = await self.get_relationships(user_id)

        return [
            int(r["user"]["id"])
            for r in rels
            if r["type"] == RelationshipType.FRIEND.value
        ]

    async def get_dms(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all DM channels for a user, including group DMs.

        This will only fetch channels the user has in their state,
        which is different than the whole list of DM channels.
        """
        dm_ids = await self.db.fetch(
            """
        SELECT dm_id
        FROM dm_channel_state
        WHERE user_id = $1
        """,
            user_id,
        )

        dm_ids = [r["dm_id"] for r in dm_ids]

        res = []

        for dm_id in dm_ids:
            dm_chan = await self.storage.get_dm(dm_id, user_id)
            res.append(dm_chan)

        return res

    async def get_read_state(self, user_id: int) -> List[Dict[str, Any]]:
        """Get the read state for a user."""
        rows = await self.db.fetch(
            """
        SELECT channel_id, last_message_id, mention_count
        FROM user_read_state
        WHERE user_id = $1
        """,
            user_id,
        )

        res = []

        for row in rows:
            drow = dict(row)

            drow["id"] = str(drow["channel_id"])
            drow.pop("channel_id")

            drow["last_message_id"] = str(drow["last_message_id"])

            res.append(drow)

        return res

    async def _get_chan_overrides(self, user_id: int, guild_id: int) -> List:
        chan_overrides = []

        overrides = await self.db.fetch(
            """
        SELECT channel_id::text, muted, message_notifications
        FROM guild_settings_channel_overrides
        WHERE
            user_id = $1
        AND guild_id = $2
        """,
            user_id,
            guild_id,
        )

        for chan_row in overrides:
            dcrow = dict(chan_row)
            chan_overrides.append(dcrow)

        return chan_overrides

    async def get_guild_settings_one(self, user_id: int, guild_id: int) -> dict:
        """Get guild settings information for a single guild."""
        row = await self.db.fetchrow(
            """
        SELECT guild_id::text, suppress_everyone, muted,
               message_notifications, mobile_push
        FROM guild_settings
        WHERE user_id = $1 AND guild_id = $2
        """,
            user_id,
            guild_id,
        )

        if not row:
            await self.db.execute(
                """
            INSERT INTO guild_settings (user_id, guild_id)
            VALUES ($1, $2)
            """,
                user_id,
                guild_id,
            )

            return await self.get_guild_settings_one(user_id, guild_id)

        gid = int(row["guild_id"])
        drow = dict(row)
        chan_overrides = await self._get_chan_overrides(user_id, gid)
        return {**drow, **{"channel_overrides": chan_overrides}}

    async def get_guild_settings(self, user_id: int):
        """Get the specific User Guild Settings,
        for all guilds a user is on."""

        res = []

        settings = await self.db.fetch(
            """
        SELECT guild_id::text, suppress_everyone, muted,
               message_notifications, mobile_push
        FROM guild_settings
        WHERE user_id = $1
        """,
            user_id,
        )

        for row in settings:
            gid = int(row["guild_id"])
            drow = dict(row)

            chan_overrides = await self._get_chan_overrides(user_id, gid)

            res.append({**drow, **{"channel_overrides": chan_overrides}})

        return res

    async def get_user_guilds(self, user_id: int) -> List[int]:
        """Get all guild IDs a user is on."""
        guild_ids = await self.db.fetch(
            """
        SELECT guild_id
        FROM members
        WHERE user_id = $1
        """,
            user_id,
        )

        return [row["guild_id"] for row in guild_ids]

    async def get_mutual_guilds(self, user_id: int, peer_id: int) -> List[int]:
        """Get a list of guilds two separate users
        have in common."""
        if user_id == peer_id:
            # if we are trying to query the mutual guilds with ourselves, we
            # only need to give the list of guilds we are on.

            # doing the INTERSECT has some edge-cases that can fuck up testing,
            # such as a user querying its own profile card while they are
            # not in any guilds.

            return await self.get_user_guilds(user_id) or [0]

        mutual_guilds = await self.db.fetch(
            """
        SELECT guild_id FROM members WHERE user_id = $1
        INTERSECT
        SELECT guild_id FROM members WHERE user_id = $2
        """,
            user_id,
            peer_id,
        )

        mutual_guilds = [r["guild_id"] for r in mutual_guilds]

        return mutual_guilds

    async def are_friends_with(self, user_id: int, peer_id: int) -> bool:
        """Return if two people are friends.

        This returns false even if there is a friend request.
        """
        return await self.db.fetchval(
            """
        SELECT
            (
                SELECT EXISTS(
                    SELECT rel_type
                    FROM relationships
                    WHERE user_id = $1
                      AND peer_id = $2
                      AND rel_type = 1
                )
            )
            AND
            (
                SELECT EXISTS(
                    SELECT rel_type
                    FROM relationships
                    WHERE user_id = $2
                      AND peer_id = $1
                      AND rel_type = 1
                )
            )
        """,
            user_id,
            peer_id,
        )

    async def get_gdms_internal(self, user_id) -> List[int]:
        """Return a list of Group DM IDs the user is a member of."""
        rows = await self.db.fetch(
            """
        SELECT id
        FROM group_dm_members
        WHERE member_id = $1
        """,
            user_id,
        )

        return [r["id"] for r in rows]

    async def get_gdms(self, user_id) -> List[Dict[str, Any]]:
        """Get list of group DMs a user is in."""
        gdm_ids = await self.get_gdms_internal(user_id)

        res = []

        for gdm_id in gdm_ids:
            res.append(await self.storage.get_channel(gdm_id, user_id=user_id))

        return res
