"""
Main code for Lazy Guild implementation in litecord.
"""
import pprint
from collections import defaultdict
from typing import Any, List, Dict

from logbook import Logger

from .dispatcher import Dispatcher

log = Logger(__name__)


class GuildMemberList:
    """This class stores the current member list information
    for a guild (by channel).

    As channels can have different sets of roles that can
    read them and so, different lists, this is more of a
    "channel member list" than a guild member list.

    Attributes
    ----------
    main_lg: LazyGuildDispatcher
        Main instance of :class:`LazyGuildDispatcher`,
        so that we're able to use things such as :class:`Storage`.
    guild_id: int
        The Guild ID this instance is referring to.
    channel_id: int
        The Channel ID this instance is referring to.
    member_list: List
        The actual member list information.
    state: set
        The set of session IDs that are subscribed to the guild.

        User IDs being used as the identifier in GuildMemberList
        is a wrong assumption. It is true Discord rolled out
        lazy guilds to all of the userbase, but users that are bots,
        for example, can still rely on PRESENCE_UPDATEs.
    """
    def __init__(self, guild_id: int,
                 channel_id: int, main_lg):
        self.main_lg = main_lg
        self.guild_id = guild_id
        self.channel_id = channel_id

        # a really long chain of classes to get
        # to the storage instance...
        main = main_lg.main_dispatcher
        self.storage = main.app.storage
        self.presence = main.app.presence
        self.state_man = main.app.state_manager

        self.member_list = None
        self.items = None

        #: holds the state of subscribed shards
        #  to this channels' member list
        self.state = set()

    async def _init_check(self):
        """Check if the member list is initialized before
        messing with it."""
        if self.member_list is None:
            await self._init_member_list()

    async def get_roles(self) -> List[Dict[str, Any]]:
        """Get role information, but only:
         - the ID
         - the name
         - the position
        
        of all HOISTED roles."""
        # TODO: write own query for this
        # TODO: calculate channel overrides
        roles = await self.storage.get_role_data(self.guild_id)

        return [{
            'id': role['id'],
            'name': role['name'],
            'position': role['position']
        } for role in roles if role['hoist']]

    async def _init_member_list(self):
        """Fill in :attr:`GuildMemberList.member_list`
        with information about the guilds' members."""
        member_ids = await self.storage.get_member_ids(self.guild_id)

        guild_presences = await self.presence.guild_presences(
            member_ids, self.guild_id)

        guild_roles = await self.get_roles()

        # sort by position
        guild_roles.sort(key=lambda role: role['position'])
        roleids = [r['id'] for r in guild_roles]

        # groups are:
        #  - roles that are hoisted
        #  - "online" and "offline", with "online"
        #    being for people without any roles.

        groups = roleids + ['online', 'offline']

        log.debug('{} presences, {} groups',
                  len(guild_presences), len(groups))

        group_data = {group: [] for group in groups}

        print('group data', group_data)

        def _try_hier(role_id: str, roleids: list):
            """Try to fetch a role's position in the hierarchy"""
            try:
                return roleids.index(role_id)
            except ValueError:
                # the given role isn't on a group
                # so it doesn't count for our purposes.
                return 0

        for presence in guild_presences:
            # simple group (online or offline)
            # we'll decide on the best group for the presence later on
            simple_group = ('offline'
                            if presence['status'] == 'offline'
                            else 'online')

            # get the best possible role
            roles = sorted(
                presence['roles'],
                key=lambda role_id: _try_hier(role_id, roleids)
            )

            try:
                best_role_id = roles[0]
            except IndexError:
                # no hoisted roles exist in the guild, assign
                # the @everyone role
                best_role_id = str(self.guild_id)

            print('best role', best_role_id, str(self.guild_id))
            print('simple group assign', simple_group)

            # if the best role is literally the @everyone role,
            # this user has no hoisted roles
            if best_role_id == str(self.guild_id):
                # this user has no roles, put it on online/offline
                group_data[simple_group].append(presence)
                continue

            # this user has a best_role that isn't the
            # @everyone role, so we'll put them in the respective group
            try:
                group_data[best_role_id].append(presence)
            except KeyError:
                group_data[simple_group].append(presence)

        # go through each group and sort the resulting members by display name

        members = await self.storage.get_member_data(self.guild_id)
        member_nicks = {member['user']['id']: member.get('nick')
                        for member in members}

        # now we'll sort each group by their display name
        # (can be their current nickname OR their username
        #  if no nickname is set)
        print('pre-sorted group data')
        pprint.pprint(group_data)

        for _, group_list in group_data.items():
            def display_name(presence: dict) -> str:
                uid = presence['user']['id']

                uname = presence['user']['username']
                nick = member_nicks[uid]

                return nick or uname

            group_list.sort(key=display_name)

        pprint.pprint(group_data)

        self.member_list = {
            'groups': groups,
            'data': group_data
        }

    def get_items(self) -> list:
        """Generate the main items list,"""
        if self.member_list is None:
            return []

        if self.items:
            return self.items

        groups = self.member_list['groups']

        res = []
        for group in groups:
            members = self.member_list['data'][group]

            res.append({
                'group': {
                    'id': group,
                    'count': len(members),
                }
            })

            for member in members:
                res.append({
                    'member': member
                })

        self.items = res
        return res

    async def sub(self, session_id: str):
        """Subscribe a shard to the member list."""
        await self._init_check()
        self.state.add(session_id)

    async def unsub(self, session_id: str):
        """Unsubscribe a shard from the member list"""
        self.state.discard(session_id)

        # once we reach 0 subscribers,
        # we drop the current member list we have (for memory)
        # but keep the GuildMemberList running (as
        #  uninitialized) for a future subscriber.

        if not self.state:
            self.member_list = None

    async def shard_query(self, session_id: str, ranges: list):
        """Send a GUILD_MEMBER_LIST_UPDATE event
        for a shard that is querying about the member list.

        Paramteters
        -----------
        session_id: str
            The Session ID querying information.
        channel_id: int
            The Channel ID that we want information on.
        ranges: List[List[int]]
            ranges of the list that we want.
        """

        await self._init_check()

        # make sure this is a sane state
        state = self.state_man.fetch_raw(session_id)
        if not state:
            await self.unsub(session_id)
            return

        # since this is a sane state AND
        # trying to query, we automatically
        # subscribe the state to this list
        await self.sub(session_id)

        # TODO: subscribe shard to 'everyone'
        #       and forward the query to that list

        reply = {
            'guild_id': str(self.guild_id),

            # TODO: everyone for channels without overrides
            # channel_id for channels WITH overrides.

            'id': 'everyone',
            # 'id': str(self.channel_id),

            'groups': [
                {
                    'count': len(self.member_list['data'][group]),
                    'id': group
                } for group in self.member_list['groups']
            ],

            'ops': [],
        }

        for start, end in ranges:
            itemcount = end - start

            # ignore incorrect ranges
            if itemcount < 0:
                continue

            items = self.get_items()

            reply['ops'].append({
                'op': 'SYNC',
                'range': [start, end],
                'items': items[start:end],
            })

        # the first GUILD_MEMBER_LIST_UPDATE for a shard
        # is dispatched here.
        await state.ws.dispatch('GUILD_MEMBER_LIST_UPDATE', reply)

    async def pres_update(self, user_id: int, roles: List[str],
                          status: str, game: dict) -> List[str]:
        return list(self.state)

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

        if self.member_list is None:
            # if the list is currently uninitialized,
            # no subscribers actually happened, so
            # we can safely drop the incoming event.
            return


class LazyGuildDispatcher(Dispatcher):
    """Main class holding the member lists for lazy guilds."""
    # channel ids
    KEY_TYPE = int

    # the session ids subscribing to channels
    VAL_TYPE = str

    def __init__(self, main):
        super().__init__(main)

        self.storage = main.app.storage

        # {chan_id: gml, ...}
        self.state = {}

        #: store which guilds have their
        #  respective GMLs
        # {guild_id: [chan_id, ...], ...}
        self.guild_map = defaultdict(list)

    async def get_gml(self, channel_id: int):
        """Get a guild list for a channel ID,
        generating it if it doesn't exist."""
        try:
            return self.state[channel_id]
        except KeyError:
            guild_id = await self.storage.guild_from_channel(
                channel_id
            )

            gml = GuildMemberList(guild_id, channel_id, self)
            self.state[channel_id] = gml
            self.guild_map[guild_id].append(channel_id)
            return gml

    def get_gml_guild(self, guild_id: int) -> List[GuildMemberList]:
        """Get all member lists for a given guild."""
        return list(map(
            self.state.get,
            self.guild_map[guild_id]
        ))

    async def sub(self, chan_id, session_id):
        gml = await self.get_gml(chan_id)
        await gml.sub(session_id)

    async def unsub(self, chan_id, session_id):
        gml = await self.get_gml(chan_id)
        await gml.unsub(session_id)
