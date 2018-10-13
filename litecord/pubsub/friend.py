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

    async def dispatch(self, user_id: int, event, data):
        """Dispatch an event to all of a users' friends."""
        # all friends that are connected and subscribed
        # to the one we're dispatching from
        peer_ids = self.state[user_id]
        dispatched = 0

        for peer_id in peer_ids:
            # dispatch to the user instead of the "shards tied to a guild"
            # since relationships broadcast to all shards.
            dispatched += await self.main_dispatcher.dispatch(
                'user', peer_id, event, data)

        log.info('dispatched uid={} {!r} to {} states',
                 user_id, event, dispatched)
