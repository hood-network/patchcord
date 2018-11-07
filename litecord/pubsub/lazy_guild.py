"""
Main code for Lazy Guild implementation in litecord.
"""
import pprint
from dataclasses import dataclass, asdict
from collections import defaultdict
from typing import Any, List, Dict, Union

from logbook import Logger

from litecord.pubsub.dispatcher import Dispatcher
from litecord.permissions import (
    Permissions, overwrite_find_mix, get_permissions, role_permissions
)

log = Logger(__name__)

GroupID = Union[int, str]
Presence = Dict[str, Any]


@dataclass
class GroupInfo:
    """Store information about a specific group."""
    gid: GroupID
    name: str
    position: int
    permissions: Permissions


@dataclass
class MemberList:
    """Total information on the guild's member list."""
    groups: List[GroupInfo] = None
    group_info: Dict[GroupID, GroupInfo] = None
    data: Dict[GroupID, Presence] = None
    overwrites: Dict[int, Dict[str, Any]] = None

    def __bool__(self):
        """Return if the current member list is fully initialized."""
        list_dict = asdict(self)
        return all(v is not None for v in list_dict.values())

    def __iter__(self):
        """Iterate over all groups in the correct order.

        Yields a tuple containing :class:`GroupInfo` and
        the List[Presence] for the group.
        """
        for group in self.groups:
            yield group, self.data[group.gid]


def _to_simple_group(presence: dict) -> str:
    """Return a simple group (not a role), given a presence."""
    return 'offline' if presence['status'] == 'offline' else 'online'


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
        self.guild_id = guild_id
        self.channel_id = channel_id

        # a really long chain of classes to get
        # to the storage instance...
        self.main = main_lg
        self.storage = self.main.app.storage
        self.presence = self.main.app.presence
        self.state_man = self.main.app.state_manager

        self.list = MemberList(None, None, None, None)

        #: {session_id: set[list]}
        self.state = defaultdict(set)

    def _set_empty_list(self):
        self.list = MemberList(None, None, None, None)

    async def _init_check(self):
        """Check if the member list is initialized before
        messing with it."""
        if not self.list:
            await self._init_member_list()

    async def _fetch_overwrites(self):
        overwrites = await self.storage.chan_overwrites(self.channel_id)
        overwrites = {int(ov['id']): ov for ov in overwrites}
        self.list.overwrites = overwrites

    def _calc_member_group(self, roles: List[int], status: str):
        """Calculate the best fitting group for a member,
        given their roles and their current status."""
        try:
            # the first group in the list
            # that the member is entitled to is
            # the selected group for the member.
            group_id = next(g.gid for g in self.list.groups
                            if g.gid in roles)
        except StopIteration:
            # no group was found, so we fallback
            # to simple group"
            group_id = _to_simple_group({'status': status})

        return group_id

    async def get_roles(self) -> List[GroupInfo]:
        """Get role information, but only:
         - the ID
         - the name
         - the position
         - the permissions

        of all HOISTED roles AND roles that
        have permissions to read the channel
        being referred to this :class:`GuildMemberList`
        instance.

        The list is sorted by position.
        """
        roledata = await self.storage.db.fetch("""
        SELECT id, name, hoist, position, permissions
        FROM roles
        WHERE guild_id = $1
        """, self.guild_id)

        hoisted = [
            GroupInfo(row['id'], row['name'],
                      row['position'], row['permissions'])
            for row in roledata if row['hoist']
        ]

        # sort role list by position
        hoisted = sorted(hoisted, key=lambda group: group.position)

        # we need to store them for later on
        # for members
        await self._fetch_overwrites()

        def _can_read_chan(group: GroupInfo):
            # get the base role perms
            role_perms = group.permissions

            # then the final perms for that role if
            # any overwrite exists in the channel
            final_perms = overwrite_find_mix(
                role_perms, self.list.overwrites, group.gid)

            # update the group's permissions
            # with the mixed ones
            group.permissions = final_perms

            # if the role can read messages, then its
            # part of the group.
            return final_perms.bits.read_messages

        return list(filter(_can_read_chan, hoisted))

    async def set_groups(self):
        """Get the groups for the member list."""
        role_groups = await self.get_roles()
        role_ids = [g.gid for g in role_groups]

        self.list.groups = role_ids + ['online', 'offline']

        # inject default groups 'online' and 'offline'
        self.list.groups = role_ids + [
            GroupInfo('online', 'online', -1, -1),
            GroupInfo('offline', 'offline', -1, -1)
        ]
        self.list.group_info = {g.gid: g for g in role_groups}

    async def _pass_1(self, guild_presences: List[Presence]):
        """First pass on generating the member list.

        This assigns all presences a single group.
        """
        for presence in guild_presences:
            member_id = int(presence['user']['id'])

            # list of roles for the member
            member_roles = list(map(int, presence['roles']))

            # get the member's permissions relative to the channel
            # (accounting for channel overwrites)
            member_perms = await get_permissions(
                member_id, self.channel_id, storage=self.storage)

            if not member_perms.bits.read_messages:
                continue

            # if the member is offline, we
            # default give them the offline group.
            status = presence['status']
            group_id = ('offline' if status == 'offline'
                        else self._calc_member_group(member_roles, status))

            self.list.data[group_id].append(presence)

    async def _sort_groups(self):
        members = await self.storage.get_member_data(self.guild_id)

        # make a dictionary of member ids to nicknames
        # so we don't need to keep querying the db on
        # every loop iteration
        member_nicks = {m['user']['id']: m.get('nick')
                        for m in members}

        for group_members in self.list.data.values():
            def display_name(presence: Presence) -> str:
                uid = presence['user']['id']

                uname = presence['user']['username']
                nick = member_nicks.get(uid)

                return nick or uname

            # this should update the list in-place
            group_members.sort(key=display_name)

    async def _init_member_list(self):
        """Generate the main member list with groups."""
        member_ids = await self.storage.get_member_ids(self.guild_id)

        guild_presences = await self.presence.guild_presences(
            member_ids, self.guild_id)

        await self.set_groups()

        log.debug('{} presences, {} groups',
                  len(guild_presences),
                  len(self.list.groups))

        self.list.data = {group.gid: [] for group in self.list.groups}

        # first pass: set which presences
        # go to which groups
        await self._pass_1(guild_presences)

        # second pass: sort each group's members
        # by the display name
        await self._sort_groups()

    @property
    def items(self) -> list:
        """Main items list."""

        # TODO: maybe make this stored in the list
        # so we don't need to keep regenning?

        if not self.list:
            return []

        res = []

        # NOTE: maybe use map()?
        for group, presences in self.list:
            res.append({
                'group': {
                    'id': group.gid,
                    'count': len(presences),
                }
            })

            for presence in presences:
                res.append({
                    'member': presence
                })

        return res

    async def sub(self, _session_id: str):
        """Subscribe a shard to the member list."""
        await self._init_check()

    async def unsub(self, session_id: str):
        """Unsubscribe a shard from the member list"""
        try:
            self.state.pop(session_id)
        except KeyError:
            pass

        # once we reach 0 subscribers,
        # we drop the current member list we have (for memory)
        # but keep the GuildMemberList running (as
        #  uninitialized) for a future subscriber.

        if not self.state:
            self._set_empty_list()

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

        # a guild list with a channel id of the guild
        # represents the 'everyone' global list.
        list_id = ('everyone'
                   if self.channel_id == self.guild_id
                   else str(self.channel_id))

        # if everyone can read the channel,
        # we direct the request to the 'everyone' gml instance
        # instead of the current one.
        everyone_perms = await role_permissions(
            self.guild_id,
            self.guild_id,
            self.channel_id,
            storage=self.storage
        )

        if everyone_perms.bits.read_messages and list_id != 'everyone':
            everyone_gml = await self.main.get_gml(self.guild_id)

            return await everyone_gml.shard_query(
                session_id, ranges
            )

        await self._init_check()

        # make sure this is a sane state
        state = self.state_man.fetch_raw(session_id)
        if not state:
            await self.unsub(session_id)
            return

        reply = {
            'guild_id': str(self.guild_id),
            'id': list_id,

            'groups': [
                {
                    'count': len(presences),
                    'id': group.gid
                } for group, presences in self.list
            ],

            'ops': [],
        }

        for start, end in ranges:
            itemcount = end - start

            # ignore incorrect ranges
            if itemcount < 0:
                continue

            self.state[session_id].add((start, end))

            reply['ops'].append({
                'op': 'SYNC',
                'range': [start, end],
                'items': self.items[start:end],
            })

        # the first GUILD_MEMBER_LIST_UPDATE for a shard
        # is dispatched here.
        await state.ws.dispatch('GUILD_MEMBER_LIST_UPDATE', reply)

    async def pres_update(self, user_id: int, roles: List[str],
                          status: str, game: dict) -> List[str]:
        return list(self.state)

    async def dispatch(self, event: str, data: Any):
        """Modify the member list and dispatch the respective
        events to subscribed shards.

        GuildMemberList stores the current guilds' list
        in its :attr:`GuildMemberList.list` attribute,
        with that attribute being modified via different
        calls to :meth:`GuildMemberList.dispatch`
        """

        # if no subscribers, drop event
        if not self.list:
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

            # if we don't find a guild, we just
            # set it the same as the channel.
            if not guild_id:
                guild_id = channel_id

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

    async def unsub(self, chan_id, session_id):
        gml = await self.get_gml(chan_id)
        await gml.unsub(session_id)
