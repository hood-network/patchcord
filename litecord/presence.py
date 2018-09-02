from typing import List, Dict, Any


class PresenceManager:
    """Presence related functions."""
    def __init__(self, storage, state_manager):
        self.storage = storage
        self.state_manager = state_manager

    async def guild_presences(self, member_ids: List[int],
                              guild_id: int) -> List[Dict[Any, str]]:
        states = self.state_manager.guild_states(member_ids, guild_id)

        presences = []

        for state in states:
            member = await self.storage.get_member_data_one(
                guild_id, state.user_id)

            presences.append({
                'user': member['user'],
                'roles': member['roles'],
                'game': state.presence['game'],
                'guild_id': guild_id,
                'status': state.presence['status'],
            })

        return presences
