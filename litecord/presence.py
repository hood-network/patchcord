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

from typing import List, Dict, Any, Iterable, Optional, TYPE_CHECKING
from random import choice
from dataclasses import dataclass

if TYPE_CHECKING:
    from litecord.typing_hax import app
else:
    from quart import current_app as app

from logbook import Logger

log = Logger(__name__)


@dataclass
class BasePresence:
    status: str
    game: Optional[dict] = None

    @property
    def activities(self) -> list:
        return [self.game] if self.game else []

    @property
    def partial_dict(self) -> dict:
        return {
            "status": self.status if self.status != "unknown" else "online",
            "game": self.game,
            "since": 0,
            # hardcode all presences as coming from web
            "client_status": {"web": self.status},
            "mobile": False,
            "activities": self.activities,
        }

    def update_from_incoming_dict(self, given_presence: dict) -> None:
        given_status, given_game = (
            given_presence.get("status"),
            given_presence.get("game"),
        )

        if given_status is not None:
            assert isinstance(given_status, str)
            self.status = given_status

        if given_game is not None:
            assert isinstance(given_game, dict)
            self.game = given_game


Presence = Dict[str, Any]


def status_cmp(status: str, other_status: str) -> bool:
    """Compare if `status` is better than the `other_status`
    in the status hierarchy.
    """

    hierarchy = {
        "online": 3,
        "idle": 2,
        "dnd": 1,
        "offline": 0,
        None: -1,
        "unknown": -2,
    }

    return hierarchy[status] > hierarchy[other_status]


def _merge_state_presences(shards: list) -> BasePresence:
    """create a 'best' presence given a list of states."""
    best = BasePresence(status="offline")

    for state in shards:
        if state.presence is None:
            continue

        # shards with a better status
        # in the hierarchy are treated as best
        if status_cmp(state.presence.status, best.status):
            best.status = state.presence.status

        # if we have any game, use it
        if state.presence.game:
            best.game = state.presence.game

    return best


async def _pres(user_id: int, presence: BasePresence) -> dict:
    """Take a given base presence and convert it to a full friend presence."""
    return {**presence.partial_dict, **{"user": await app.storage.get_user(user_id)}}


class PresenceManager:
    """Presence management.

    Has common functions to deal with fetching or updating presences, including
    side-effects (events).
    """

    def __init__(self, app):
        self.storage = app.storage
        self.user_storage = app.user_storage
        self.state_manager = app.state_manager

    async def guild_presences(
        self, members: dict, guild_id: int
    ) -> List[Dict[Any, str]]:
        """Fetch all presences in a guild."""
        # this works via fetching all connected GatewayState on a guild
        # then fetching its respective member and merging that info with
        # the state's set presence.
        states = self.state_manager.guild_states([int(m["user"]["id"]) for m in members.values()], guild_id)
        presences = []

        for state in states:
            member = members[state.user_id]
            presences.append(
                {
                    **(state.presence or BasePresence(status="offline")).partial_dict,
                    **{
                        "user": member["user"],
                        "roles": member["roles"],
                        "guild_id": str(guild_id),
                    },
                }
            )

        return presences

    async def dispatch_guild_pres(
        self, guild_id: int, user_id: int, presence: BasePresence
    ):
        """Dispatch a Presence update to an entire guild."""

        member = await self.storage.get_member(guild_id, user_id)

        lists = app.lazy_guild.get_gml_guild(guild_id)

        # shards that are in lazy guilds with 'everyone'
        # enabled
        in_lazy: List[str] = []

        for member_list in lists:
            session_ids = await member_list.pres_update(
                int(member["user"]["id"]),
                {
                    "avatar": member["avatar"],
                    "banner": member["banner"],
                    "bio": member["bio"],
                    "pronouns": member["pronouns"],
                    "roles": member["roles"],
                    "status": presence.status,
                    "game": presence.game,
                    "activities": presence.activities,
                },
            )

            log.debug("Lazy Dispatch to {}", len(session_ids))

            # if we are on the 'everyone' member list, we don't
            # dispatch a PRESENCE_UPDATE for those shards.
            if member_list.channel_id == member_list.guild_id:
                in_lazy.extend(session_ids)

        event_payload = {
            **presence.partial_dict,
            **{
                "guild_id": str(guild_id),
                "user": member["user"],
                "roles": member["roles"],
            },
        }

        # given a session id, return if the session id actually connects to
        # a given user, and if the state has not been dispatched via lazy guild.
        def _session_check(session_id):
            try:
                state = self.state_manager.fetch_raw(session_id)
            except KeyError:
                return False

            uid = int(member["user"]["id"])

            # we don't want to send a presence update
            # to the same user
            return state.user_id != uid and session_id not in in_lazy

        # everyone not in lazy guild mode
        # gets a PRESENCE_UPDATE
        await app.dispatcher.guild.dispatch_filter(
            guild_id, _session_check, ("PRESENCE_UPDATE", event_payload)
        )

        return in_lazy

    async def dispatch_friends_pres(self, user_id: int, presence: BasePresence) -> None:
        """
        Dispatch a new presence to all the user' friend
        """

        user = await self.storage.get_user(user_id)
        await app.dispatcher.friend.dispatch(
            user_id,
            ("PRESENCE_UPDATE", {**presence.partial_dict, **{"user": user}}),
        )

    async def dispatch_friends_pres_filter(
        self, user: dict, filter_function, presence: BasePresence
    ):
        """
        Same as dispatch_friends_pres but passes a filter function
        Takes in a whole public user object instead of a user id
        """

        return await app.dispatcher.friend.dispatch_filter(
            int(user["id"]),
            filter_function,
            ("PRESENCE_UPDATE", {**presence.partial_dict, **{"user": user}}),
        )

    async def dispatch_pres(self, user_id: int, presence: BasePresence) -> None:
        """Dispatch a new presence to all guilds the user is in.

        Also dispatches the presence to all the users' friends
        """
        guild_ids = await self.user_storage.get_user_guilds(user_id)
        for guild_id in guild_ids:
            await self.dispatch_guild_pres(guild_id, user_id, presence)

        await self.dispatch_friends_pres(user_id, presence)

    def fetch_self_presence(self, user_id: int) -> BasePresence:
        """Fetch a presence for a specifc user.

        This is basically the same as the friend function, so let's just call that
        """
        return self.fetch_friend_presence(user_id)

    def fetch_friend_presence(self, friend_id: int) -> BasePresence:
        """Fetch a presence for a friend.

        This is a different algorithm than guild presence.
        """
        friend_states = self.state_manager.user_states(friend_id)

        if not friend_states:
            return BasePresence(status="offline")

        # filter the best shards:
        #  - all with id 0 (are the first shards in the collection) or
        #  - all shards with count = 1 (single shards)
        good_shards = list(
            filter(
                lambda state: state.current_shard == 0 or state.shard_count == 1,
                friend_states,
            )
        )

        if good_shards:
            return _merge_state_presences(good_shards)

        # if there aren't any shards with id 0
        # AND none that are single, just go with a random one.
        shard = choice([s for s in friend_states if s.presence])
        return shard.presence or BasePresence(status="offline")

    async def friend_presences(self, friends: Iterable[dict]) -> List[Presence]:
        """Fetch presences for a group of users.

        This assumes the users are friends and so
        only gets states that are single or have ID 0.
        """
        res = []
        for user in friends:
            presence = self.fetch_friend_presence(int(user["id"]))
            res.append({**presence.partial_dict, 'user': user})

        return res
