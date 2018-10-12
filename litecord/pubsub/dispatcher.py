from collections import defaultdict
from logbook import Logger

log = Logger(__name__)


class Dispatcher:
    """Pub/Sub backend dispatcher."""

    # the _ parameter is for (self)
    KEY_TYPE = lambda _, x: x
    VAL_TYPE = lambda _, x: x

    def __init__(self, main):
        self.main_dispatcher = main
        self.sm = main.state_manager
        self.app = main.app

    async def sub(self, _key, _id):
        """Subscribe an element to the channel/key."""
        raise NotImplementedError

    async def unsub(self, _key, _id):
        """Unsubscribe an elemtnt from the channel/key."""
        raise NotImplementedError

    async def dispatch(self, _key, *_args):
        """Dispatch an event to the given channel/key."""
        raise NotImplementedError

    async def reset(self, _key):
        """Reset a key from the backend."""
        raise NotImplementedError

    async def remove(self, _key):
        """Remove a key from the backend.

        The meaning from reset() and remove()
        is different, reset() is to clear all
        subscribers from the given key,
        remove() is to remove the key as well.
        """
        raise NotImplementedError

    async def _dispatch_states(self, states: list, event: str, data) -> int:
        """Dispatch an event to a list of states."""
        dispatched = 0

        for state in states:
            try:
                await state.ws.dispatch(event, data)
                dispatched += 1
            except:
                log.exception('error while dispatching')

        return dispatched


class DispatcherWithState(Dispatcher):
    """Pub/Sub backend with a state dictionary.

    This class was made to decrease the amount
    of boilerplate code on Pub/Sub backends
    that have that dictionary.
    """
    def __init__(self, main):
        super().__init__(main)

        self.state = defaultdict(set)

    async def sub(self, key, identifier):
        self.state[key].add(identifier)

    async def unsub(self, key, identifier):
        self.state[key].discard(identifier)

    async def reset(self, key):
        self.state[key] = set()

    async def remove(self, key):
        try:
            self.state.pop(key)
        except KeyError:
            pass

    async def dispatch(self, key, *args):
        raise NotImplementedError
