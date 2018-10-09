from .dispatcher import Dispatcher


class UserDispatcher(Dispatcher):
    KEY_TYPE = int

    async def dispatch(self, user_id: int, event, data):
        states = self.sm.user_states(user_id)
        return await self._dispatch_states(states, event, data)
