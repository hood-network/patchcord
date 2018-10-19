from collections import defaultdict
from typing import Any

from logbook import Logger

from .dispatcher import Dispatcher

log = Logger(__name__)


class GuildMemberList():
    def __init__(self, guild_id: int):
        self.guild_id = guild_id

        # TODO: initialize list with actual member info
        self._uninitialized = True
        self.member_list = []

        #: holds the state of subscribed users
        self.state = set()

    async def _init_check(self):
        """Check if the member list is initialized before
        messing with it."""
        if self._uninitialized:
            await self._init_member_list()

    async def _init_member_list(self):
        """Fill in :attr:`GuildMemberList.member_list`
        with information about the guilds' members."""
        pass

    async def sub(self, user_id: int):
        """Subscribe a user to the member list."""
        await self._init_check()
        self.state.add(user_id)

    async def unsub(self, user_id: int):
        """Unsubscribe a user from the member list"""
        self.state.discard(user_id)

        # once we reach 0 subscribers,
        # we drop the current member list we have (for memory)
        # but keep the GuildMemberList running (as
        #  uninitialized) for a future subscriber.

        if not self.state:
            self.member_list = []
            self._uninitialized = True

    async def dispatch(self, event: str, data: Any):
        """The dispatch() method here, instead of being
        about dispatching a single event to the subscribed
        users and forgetting about it, is about storing
        the actual member list information so that we
        can generate the respective events to the users.

        GuildMemberList stores the current guilds' list
        in its :attr:`GuildMemberList.member_list` attribute,
        with that attribute being modified via different
        calls to :meth:`GuildMemberList.dispatch`
        """

        if self._uninitialized:
            # if the list is currently uninitialized,
            # no subscribers actually happened, so
            # we can safely drop the incoming event.
            return


class LazyGuildDispatcher(Dispatcher):
    """Main class holding the member lists for lazy guilds."""
    KEY_TYPE = int
    VAL_TYPE = int

    def __init__(self, main):
        super().__init__(main)
        self.state = defaultdict(GuildMemberList)

    async def sub(self, guild_id, user_id):
        await self.state[guild_id].sub(user_id)

    async def unsub(self, guild_id, user_id):
        await self.state[guild_id].unsub(user_id)

    async def dispatch(self, guild_id: int, event: str, data):
        """Dispatch an event to the member list.

        GuildMemberList will make sure of converting it to
        GUILD_MEMBER_LIST_UPDATE events.
        """
        member_list = self.state[guild_id]
        await member_list.dispatch(event, data)

