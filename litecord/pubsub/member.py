from .dispatcher import Dispatcher


class MemberDispatcher(Dispatcher):
    KEY_TYPE = int
    VAL_TYPE = int

    async def dispatch(self, guild_id: int, user_id: int, event, data):
        """Dispatch a single event to a member.

        This is shard-aware.
        """
        # fetch shards
        states = self.sm.fetch_states(user_id, guild_id)

        if not states:
            await self.main_dispatcher.unsub('guild', guild_id, user_id)
            return

        await self._dispatch_states(states, event, data)
