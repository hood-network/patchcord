from logbook import Logger

log = Logger(__name__)


class Dispatcher:
    """Main dispatcher class."""
    KEY_TYPE = lambda x: x
    VAL_TYPE = lambda x: x

    def __init__(self, main):
        self.main_dispatcher = main
        self.sm = main.state_manager

    async def sub(self, _key, _id):
        raise NotImplementedError

    async def unsub(self, _key, _id):
        raise NotImplementedError

    async def dispatch(self, _key, *_args, **_kwargs):
        raise NotImplementedError

    async def _dispatch_states(self, states: list, event: str, data) -> int:
        dispatched = 0

        for state in states:
            try:
                await state.ws.dispatch(event, data)
                dispatched += 1
            except:
                log.exception('error while dispatching')

        return dispatched
