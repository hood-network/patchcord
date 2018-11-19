from .dispatcher import Dispatcher


class UserDispatcher(Dispatcher):
    """User backend for Pub/Sub."""
    KEY_TYPE = int

    async def dispatch_filter(self, user_id: int, func, event, data):
        """Dispatch an event to all shards of a user."""

        # filter only states where func() gives true
        states = list(filter(
            lambda state: func(state.session_id),
            self.sm.user_states(user_id)
        ))

        return await self._dispatch_states(states, event, data)

    async def dispatch(self, user_id: int, event, data):
        return await self.dispatch_filter(
            user_id,
            lambda sess_id: True,
            event, data,
        )
