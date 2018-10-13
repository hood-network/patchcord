from typing import List, Dict, Any
from collections import defaultdict

from logbook import Logger

from .state import GatewayState


log = Logger(__name__)


class StateManager:
    """Manager for gateway state information."""

    def __init__(self):
        # {
        #  user_id: {
        #   session_id: GatewayState,
        #   session_id_2: GatewayState, ...
        #  },
        #  user_id_2: {}, ...
        # }
        self.states = defaultdict(dict)

    def insert(self, state: GatewayState):
        """Insert a new state object."""
        user_states = self.states[state.user_id]

        log.debug('inserting state: {!r}', state)
        user_states[state.session_id] = state

    def fetch(self, user_id: int, session_id: str) -> GatewayState:
        """Fetch a state object from the manager.

        Raises
        ------
        KeyError
            When the user_id or session_id
            aren't found in the store.
        """
        return self.states[user_id][session_id]

    def remove(self, state):
        """Remove a state from the registry"""
        if not state:
            return

        try:
            log.debug('removing state: {!r}', state)
            self.states[state.user_id].pop(state.session_id)
        except KeyError:
            pass

    def fetch_states(self, user_id: int, guild_id: int) -> List[GatewayState]:
        """Fetch all states that are tied to a guild."""
        states = []

        for state in self.states[user_id].values():
            # find out if we are the shard for the guild id
            # this works if shard_count == 1 (the default for
            # single gw connections) since N % 1 is always 0
            shard_id = (guild_id >> 22) % state.shard_count

            if shard_id == state.current_shard:
                states.append(state)

        return states

    def user_states(self, user_id: int) -> List[GatewayState]:
        """Fetch all states tied to a single user."""
        return list(self.states[user_id].values())

    def guild_states(self, member_ids: List[int],
                     guild_id: int) -> List[GatewayState]:
        """Fetch all possible states about members in a guild."""
        states = []

        for member_id in member_ids:
            member_states = self.fetch_states(member_id, guild_id)

            # member_states is empty if the user never logged in
            # since server start, so we need to add a dummy state
            if not member_states:
                dummy_state = GatewayState(
                    session_id='',
                    user_id=member_id,
                    presence={
                        'afk': False,
                        'status': 'offline',
                        'game': None,
                        'since': 0
                    }
                )

                states.append(dummy_state)
                continue

            # push all available member states to the result
            # array
            states.extend(member_states)

        return states
