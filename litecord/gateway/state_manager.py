import logging

from typing import List
from collections import defaultdict

from .state import GatewayState


log = logging.getLogger(__name__)


class StateManager:
    """Manager for gateway state information."""

    def __init__(self):
        self.states = defaultdict(dict)

    def insert(self, state: GatewayState):
        """Insert a new state object."""
        user_states = self.states[state.user_id]

        log.info(f'Inserting state {state!r}')
        user_states[state.session_id] = state

    def fetch(self, user_id: int, session_id: str) -> GatewayState:
        """Fetch a state object from the registry."""
        return self.states[user_id][session_id]

    def remove(self, state):
        """Remove a state from the registry"""
        if not state:
            return

        try:
            log.info(f'Removing state {state!r}')
            self.states[state.user_id].pop(state.session_id)
        except KeyError:
            pass

    def fetch_states(self, user_id, guild_id) -> List[GatewayState]:
        """Fetch all states that are tied to a guild."""
        states = []

        for state in self.states[user_id]:
            shard_id = (guild_id >> 22) % state.shard_count

            if shard_id == state.current_shard:
                states.append(state)

        return states
