from typing import List, Dict, Any
from random import choice

from logbook import Logger

log = Logger(__name__)


def status_cmp(status: str, other_status: str) -> bool:
    """Compare if `status` is better than the `other_status`
    in the status hierarchy.
    """

    hierarchy = {
        'online': 3,
        'idle': 2,
        'dnd': 1,
        'offline': 0,
        None: -1,
    }

    return hierarchy[status] > hierarchy[other_status]


def _best_presence(shards):
    """Find the 'best' presence given a list of GatewayState."""
    best = {'status': None, 'game': None}

    for state in shards:
        presence = state.presence

        status = presence['status']

        if not presence:
            continue

        # shards with a better status
        # in the hierarchy are treated as best
        if status_cmp(status, best['status']):
            best['status'] = status

        # if we have any game, use it
        if presence['game'] is not None:
            best['game'] = presence['game']

    # best['status'] is None when no
    # status was good enough.
    return None if not best['status'] else best


async def _pres(storage, user_id: int, status_obj: dict) -> dict:
    ext = {
        'user': await storage.get_user(user_id),
        'activities': [],
    }

    return {**status_obj, **ext}


class PresenceManager:
    """Presence related functions."""
    def __init__(self, storage, state_manager, dispatcher):
        self.storage = storage
        self.state_manager = state_manager
        self.dispatcher = dispatcher

    async def guild_presences(self, member_ids: List[int],
                              guild_id: int) -> List[Dict[Any, str]]:
        """Fetch all presences in a guild."""
        states = self.state_manager.guild_states(member_ids, guild_id)

        presences = []

        for state in states:
            member = await self.storage.get_member_data_one(
                guild_id, state.user_id)

            game = state.presence.get('game', None)

            # only use the data we need.
            presences.append({
                'user': member['user'],
                'roles': member['roles'],
                'guild_id': str(guild_id),

                # basic presence
                'status': state.presence['status'],

                # game is an activity object, for rich presence
                'game': game,
                'activities': [game] if game else []
            })

        return presences

    async def dispatch_guild_pres(self, guild_id: int,
                                  user_id: int, new_state: dict):
        """Dispatch a Presence update to an entire guild."""
        state = dict(new_state)

        member = await self.storage.get_member_data_one(guild_id, user_id)

        game = state['game']

        lazy_guild_store = self.dispatcher.backends['lazy_guild']
        lists = lazy_guild_store.get_gml_guild(guild_id)

        # shards that are in lazy guilds with 'everyone'
        # enabled
        in_lazy = []

        for member_list in lists:
            session_ids = await member_list.pres_update(
                int(member['user']['id']),
                {
                    'roles': member['roles'],
                    'status': state['status'],
                    'game': game
                }
            )

            log.debug('Lazy Dispatch to {}',
                      len(session_ids))

            # if we are on the 'everyone' member list, we don't
            # dispatch a PRESENCE_UPDATE for those shards.
            if member_list.channel_id == member_list.guild_id:
                in_lazy.extend(session_ids)

        pres_update_payload = {
            'user': member['user'],
            'roles': member['roles'],
            'guild_id': str(guild_id),

            'status': state['status'],

            # rich presence stuff
            'game': game,
            'activities': [game] if game else []
        }

        def _sane_session(session_id):
            state = self.state_manager.fetch_raw(session_id)
            uid = int(member['user']['id'])

            if not state:
                return False

            # we don't want to send a presence update
            # to the same user
            return (state.user_id != uid and
                    session_id not in in_lazy)

        # everyone not in lazy guild mode
        # gets a PRESENCE_UPDATE
        await self.dispatcher.dispatch_filter(
            'guild', guild_id,
            _sane_session,

            'PRESENCE_UPDATE', pres_update_payload
        )

        return in_lazy

    async def dispatch_pres(self, user_id: int, state: dict):
        """Dispatch a new presence to all guilds the user is in.

        Also dispatches the presence to all the users' friends
        """
        if state['status'] == 'invisible':
            state['status'] = 'offline'

        # TODO: shard-aware
        guild_ids = await self.storage.get_user_guilds(user_id)

        for guild_id in guild_ids:
            await self.dispatch_guild_pres(
                guild_id, user_id, state)

        # dispatch to all friends that are subscribed to them
        user = await self.storage.get_user(user_id)
        game = state['game']

        await self.dispatcher.dispatch(
            'friend', user_id, 'PRESENCE_UPDATE', {
                'user': user,
                'status': state['status'],

                # rich presence stuff
                'game': game,
                'activities': [game] if game else []
            })

    async def friend_presences(self, friend_ids: int) -> List[Dict[str, Any]]:
        """Fetch presences for a group of users.

        This assumes the users are friends and so
        only gets states that are single or have ID 0.
        """
        storage = self.storage
        res = []

        for friend_id in friend_ids:
            friend_states = self.state_manager.user_states(friend_id)

            if not friend_states:
                # append offline
                res.append(await _pres(storage, friend_id, {
                    'afk': False,
                    'status': 'offline',
                    'game': None,
                    'since': 0
                }))

                continue

            # filter the best shards:
            #  - all with id 0 (are the first shards in the collection) or
            #  - all shards with count = 1 (single shards)
            good_shards = list(filter(
                lambda state: state.shard[0] == 0 or state.shard[1] == 1,
                friend_states
            ))

            if good_shards:
                best_pres = _best_presence(good_shards)
                best_pres = await _pres(storage, friend_id, best_pres)
                res.append(best_pres)
                continue

            # if there aren't any shards with id 0
            # AND none that are single, just go with a random
            shard = choice(friend_states)
            res.append(await _pres(storage, friend_id, shard.presence))

        return res
