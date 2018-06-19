from .state import GatewayState


class StateManager:
    """Manager for gateway state information."""
    def __init__(self):
        self.states = {}

    def insert(self, state: GatewayState):
        """Insert a new state object."""
        user_states = self.states[state.user_id]
        user_states[state.session_id] = state

    def fetch(self, user_id: int, session_id: str) -> GatewayState:
        """Fetch a state object from the registry."""
        return self.states[user_id][session_id]
