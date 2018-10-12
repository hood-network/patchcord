from .dispatcher import Dispatcher


class UserDispatcher(Dispatcher):
    """User backend for Pub/Sub."""
    KEY_TYPE = int

    async def dispatch(self, user_id: int, event, data):
        """Dispatch an event to all shards of a user."""
        states = self.sm.user_states(user_id)
        return await self._dispatch_states(states, event, data)
