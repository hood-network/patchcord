from logbook import Logger

from .dispatcher import DispatcherWithState

log = Logger(__name__)


class FriendDispatcher(DispatcherWithState):
    """Friend Pub/Sub logic.

    When connecting, a client will subscribe to all their friends
    channels. If that friend updates their presence, it will be
    broadcasted through that channel to basically all their friends.
    """
    KEY_TYPE = int
    VAL_TYPE = int

    async def dispatch_filter(self, user_id: int, func, event, data):
        """Dispatch an event to all of a users' friends."""
        peer_ids = self.state[user_id]
        sessions = []

        for peer_id in peer_ids:
            # dispatch to the user instead of the "shards tied to a guild"
            # since relationships broadcast to all shards.
            sessions.extend(
                await self.main_dispatcher.dispatch_filter(
                    'user', peer_id, func, event, data)
            )

        log.info('dispatched uid={} {!r} to {} states',
                 user_id, event, len(sessions))

        return sessions

    async def dispatch(self, user_id, event, data):
        return await self.dispatch_filter(
            user_id,
            lambda sess_id: True,
            event, data,
        )
