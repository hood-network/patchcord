from typing import List, Dict, Any


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

            print('state:', state)
            print('state.presence:', state.presence)

            # only use the data we need.
            presences.append({
                'user': member['user'],
                'roles': member['roles'],
                'guild_id': guild_id,

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

        if state['status'] == 'invisible':
            state['status'] = 'offline'

        member = await self.storage.get_member_data_one(guild_id, user_id)

        game = state['game']

        await self.dispatcher.dispatch_guild(
            guild_id, 'PRESENCE_UPDATE', {
                'user': member['user'],
                'roles': member['roles'],
                'guild_id': guild_id,

                'status': state['status'],

                # rich presence stuff
                'game': game,
                'activities': [game] if game else []
            }
        )

    async def dispatch_pres(self, user_id: int, state):
        """Dispatch a new presence to all guilds the user is in."""
        # TODO: account for sharding
        guild_ids = await self.storage.get_user_guilds(user_id)

        for guild_id in guild_ids:
            await self.dispatch_guild_pres(guild_id, user_id, state)
