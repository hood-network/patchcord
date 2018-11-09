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
from litecord.utils import index_by_func

log = Logger(__name__)

GroupID = Union[int, str]
Presence = Dict[str, Any]

# TODO: move this constant out of the lazy_guild module
MAX_ROLES = 250


@dataclass
class GroupInfo:
    """Store information about a specific group."""
    gid: GroupID
    name: str
    position: int
    permissions: Permissions


@dataclass
class MemberList:
    """Total information on the guild's member list.

    Attributes
    ----------
    groups: List[:class:`GroupInfo`]
        List with all group information, sorted
        by their actual position in the member list.
    data:
        Actual dictionary holding a list of presences
        that are connected to the given group.
    overwrites:
        Holds the channel overwrite information
        for the list (a list is tied to a single
        channel, and since only roles with Read Messages
        can be in the list, we need to store that information)
    """
    groups: List[GroupInfo] = None

    #: this attribute is not actively used
    #  but i'm keeping it here to future-proof
    #  in the case where we need to fetch info
    #  by the group id.
    group_info: Dict[GroupID, GroupInfo] = None
    data: Dict[GroupID, List[Presence]] = None
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
        if not self.groups:
            return

        for group in self.groups:
            yield group, self.data[group.gid]


@dataclass
class Operation:
    """Represents a member list operation."""
    list_op: str
    params: Dict[str, Any]

    @property
    def to_dict(self) -> dict:
        """Return a dictionary representation of the operation."""
        res = {
            'op': self.list_op
        }

        if self.list_op == 'SYNC':
            res['items'] = self.params['items']

        if self.list_op in ('SYNC', 'INVALIDATE'):
            res['range'] = self.params['range']

        if self.list_op in ('INSERT', 'DELETE', 'UPDATE'):
            res['index'] = self.params['index']

        if self.list_op in ('INSERT', 'UPDATE'):
            res['item'] = self.params['item']

        return res


def _to_simple_group(presence: dict) -> str:
    """Return a simple group (not a role), given a presence."""
    return 'offline' if presence['status'] == 'offline' else 'online'


def display_name(member_nicks: Dict[str, str], presence: Presence) -> str:
    """Return the display name of a presence.

    Used to sort groups.
    """
    uid = presence['user']['id']

    uname = presence['user']['username']
    nick = member_nicks.get(uid)

    return nick or uname


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

        self.main = main_lg
        self.list = MemberList(None, None, None, None)

        #: store the states that are subscribed to the list
        #  type is{session_id: set[list]}
        self.state = defaultdict(set)

    @property
    def loop(self):
        """Get the main asyncio loop instance."""
        return self.main.app.loop

    @property
    def storage(self):
        """Get the global :class:`Storage` instance."""
        return self.main.app.storage

    @property
    def presence(self):
        """Get the global :class:`PresenceManager` instance."""
        return self.main.app.presence

    @property
    def state_man(self):
        """Get the global :class:`StateManager` instance."""
        return self.main.app.state_manager

    @property
    def list_id(self):
        """get the id of the member list."""
        return ('everyone'
                if self.channel_id == self.guild_id
                else str(self.channel_id))

    def _set_empty_list(self):
        """Set the member list as being empty."""
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

    def _can_read_chan(self, group: GroupInfo):
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

        # we need to store them since
        # we have incoming presences to manage.
        await self._fetch_overwrites()
        return list(filter(self._can_read_chan, hoisted))

    async def set_groups(self):
        """Get the groups for the member list."""
        role_groups = await self.get_roles()
        role_ids = [g.gid for g in role_groups]

        self.list.groups = role_ids + ['online', 'offline']

        # inject default groups 'online' and 'offline'

        # their position is always going to be the last ones.
        self.list.groups = role_ids + [
            GroupInfo('online', 'online', MAX_ROLES + 1, 0),
            GroupInfo('offline', 'offline', MAX_ROLES + 2, 0)
        ]

        self.list.group_info = {g.gid: g for g in role_groups}

    async def get_group(self, member_id: int,
                        roles: List[Union[str, int]],
                        status: str) -> int:
        """Return a fitting group ID for the user."""
        member_roles = list(map(int, roles))

        # get the member's permissions relative to the channel
        # (accounting for channel overwrites)
        member_perms = await get_permissions(
            member_id, self.channel_id, storage=self.storage)

        if not member_perms.bits.read_messages:
            return None

        # if the member is offline, we
        # default give them the offline group.
        group_id = ('offline' if status == 'offline'
                    else self._calc_member_group(member_roles, status))

        return group_id

    async def _pass_1(self, guild_presences: List[Presence]):
        """First pass on generating the member list.

        This assigns all presences a single group.
        """
        for presence in guild_presences:
            member_id = int(presence['user']['id'])

            group_id = await self.get_group(
                member_id, presence['roles'], presence['status']
            )

            self.list.data[group_id].append(presence)

    async def get_member_nicks_dict(self) -> dict:
        """Get a dictionary with nickname information."""
        members = await self.storage.get_member_data(self.guild_id)

        # make a dictionary of member ids to nicknames
        # so we don't need to keep querying the db on
        # every loop iteration
        member_nicks = {m['user']['id']: m.get('nick')
                        for m in members}

        return member_nicks

    async def _sort_groups(self):
        member_nicks = await self.get_member_nicks_dict()

        for group_members in self.list.data.values():

            # this should update the list in-place
            group_members.sort(
                key=lambda p: display_name(member_nicks, p))

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

    def unsub(self, session_id: str):
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

    def get_state(self, session_id: str):
        """Get the state for a session id."""
        try:
            state = self.state_man.fetch_raw(session_id)
            return state
        except KeyError:
            self.unsub(session_id)
            return

    async def _dispatch_sess(self, session_ids: List[str],
                             operations: List[Operation]):

        # construct the payload to dispatch
        payload = {
            'id': self.list_id,
            'guild_id': str(self.guild_id),

            'groups': [
                {
                    'count': len(presences),
                    'id': group.gid
                } for group, presences in self.list
            ],

            'ops': [
                operation.to_dict
                for operation in operations
            ]
        }

        states = map(self.get_state, session_ids)
        states = filter(lambda state: state is not None, states)

        dispatched = []

        for state in states:
            await state.ws.dispatch(
                'GUILD_MEMBER_LIST_UPDATE', payload)

            dispatched.append(state.session_id)

        return dispatched

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
        list_id = self.list_id

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

        ops = []

        for start, end in ranges:
            itemcount = end - start

            # ignore incorrect ranges
            if itemcount < 0:
                continue

            self.state[session_id].add((start, end))

            ops.append(Operation('SYNC', {
                'range': [start, end],
                'items': self.items[start:end]
            }))

        await self._dispatch_sess([session_id], ops)

    def get_item_index(self, user_id: Union[str, int]):
        """Get the item index a user is on."""
        def _get_id(item):
            # item can be a group item or a member item
            return item.get('member', {}).get('user', {}).get('id')

        # get the updated item's index
        return index_by_func(
            lambda p: _get_id(p) == str(user_id),
            self.items
        )

    def state_is_subbed(self, item_index, session_id: str) -> bool:
        """Return if a state's ranges include the given
        item index."""

        ranges = self.state[session_id]

        for range_start, range_end in ranges:
            if range_start <= item_index <= range_end:
                return True

        return False

    def get_subs(self, item_index: int) -> filter:
        """Get the list of subscribed states to a given item."""
        return filter(
            lambda sess_id: self.state_is_subbed(item_index, sess_id),
            self.state.keys()
        )

    async def _pres_update_simple(self, user_id: int):
        item_index = self.get_item_index(user_id)

        if item_index is None:
            log.warning('lazy guild got invalid pres update uid={}',
                        user_id)
            return []

        item = self.items[item_index]
        session_ids = self.get_subs(item_index)

        # simple update means we just give an UPDATE
        # operation
        return await self._dispatch_sess(
            session_ids,
            [
                Operation('UPDATE', {
                    'index': item_index,
                    'item': item,
                })
            ]
        )

    async def _pres_update_complex(self, user_id: int,
                                   old_group: str, old_index: int,
                                   new_group: str):
        """Move a member between groups."""
        log.debug('complex update: uid={} old={} old_idx={} new={}',
                  user_id, old_group, old_index, new_group)
        old_group_presences = self.list.data[old_group]
        old_item_index = self.get_item_index(user_id)

        # make a copy of current presence to insert in the new group
        current_presence = dict(old_group_presences[old_index])

        # step 1: remove the old presence (old_index is relative
        # to the group, and not the items list)
        del old_group_presences[old_index]

        # we need to insert current_presence to the new group
        # but we also need to calculate its index to insert on.
        presences = self.list.data[new_group]

        best_index = 0
        member_nicks = await self.get_member_nicks_dict()
        current_name = display_name(member_nicks, current_presence)

        # go through each one until we find the best placement
        for presence in presences:
            name = display_name(member_nicks, presence)

            print(name, current_name, name < current_name)

            # TODO: check if this works
            if name < current_name:
                break

            best_index += 1

        # insert the presence at the index
        presences.insert(best_index + 1, current_presence)

        new_item_index = self.get_item_index(user_id)

        log.debug('assigned new item index {} to uid {}',
                  new_item_index, user_id)

        session_ids_old = self.get_subs(old_item_index)
        session_ids_new = self.get_subs(new_item_index)

        # dispatch events to both the old states and
        # new states.
        return await self._dispatch_sess(
            # inefficient, but necessary since we
            # want to merge both session ids.
            list(session_ids_old) + list(session_ids_new),
            [
                Operation('DELETE', {
                    'index': old_item_index,
                }),

                Operation('INSERT', {
                    'index': new_item_index,
                    'item': {
                        'member': current_presence
                    }
                })
            ]
        )

    async def pres_update(self, user_id: int,
                          partial_presence: Dict[str, Any]):
        """Update a presence inside the member list.

        There are 4 types of updates that can happen for a user in a group:
         - from 'offline' to any
         - from any to 'offline'
         - from any to any
         - from G to G (with G being any group)

        any: 'online' | role_id

        All first, second, and third updates are 'complex' updates,
        which means we'll have to change the group the user is on
        to account for them.

        The fourth is a 'simple' change, since we're not changing
        the group a user is on, and so there's less overhead
        involved.
        """
        await self._init_check()

        old_group, old_index, old_presence = None, None, None

        for group, presences in self.list:
            p_idx = index_by_func(
                lambda p: p['user']['id'] == str(user_id),
                presences)

            log.debug('p_idx for group {!r} = {}',
                      group.gid, p_idx)

            if p_idx is None:
                log.debug('skipping group {}', group)
                continue

            # make a copy since we're modifying in-place
            old_group = group.gid
            old_index = p_idx
            old_presence = dict(presences[p_idx])

            # be ready if it is a simple update
            presences[p_idx].update(partial_presence)
            break

        if not old_group:
            log.warning('pres update with unknown old group uid={}',
                        user_id)
            return []

        roles = partial_presence.get('roles', old_presence['roles'])
        new_status = partial_presence.get('status', old_presence['status'])

        new_group = await self.get_group(user_id, roles, new_status)

        log.debug('pres update: gid={} cid={} old_g={} new_g={}',
                  self.guild_id, self.channel_id, old_group, new_group)

        # if we're going to the same group,
        # treat this as a simple update
        if old_group == new_group:
            return await self._pres_update_simple(user_id)

        return await self._pres_update_complex(
            user_id, old_group, old_index, new_group)

    async def new_role(self, role: dict):
        """Add a new role to the list.

        Only adds the new role to the list if the role
        has the necessary permissions to start with.
        """
        group_id = int(role['id'])

        new_group = GroupInfo(group_id, role['name'],
                              role['position'], role['permisions'])

        # check if new role has good perms
        await self._fetch_overwrites()

        if not self._can_read_chan(new_group):
            log.info('ignoring incoming group {}', new_group)
            return

        # maintain role sorting
        self.list.groups.insert(role['position'], new_group)

        # since this is a new group, we can set it
        # as a new empty list (as nobody is in the
        # new role by default)

        # NOTE: maybe that assumption changes
        # when bots come along.
        self.list.data[new_group.gid] = []

    def _get_role_as_group_idx(self, role_id: int) -> int:
        """Get a group index representing the given role id.

        Returns
        -------
        int
            Representing the ID of the role inside the
            group list.

        None
            If any of those occour:
             - member list is uninitialized.
             - role is not found inside the group list.
        """
        if not self.list:
            log.warning('uninitialized list for rid={}',
                        role_id)
            return None

        groups_idx = index_by_func(
            lambda g: g.gid == role_id,
            self.list.groups
        )

        if groups_idx is None:
            log.info('ignoring rid={}, unknown group',
                     role_id)
            return None

        return groups_idx

    async def role_pos_update(self, role: dict):
        """Change a role's position if it is in the group list
        to start with.

        This resorts the entire group list, which might be
        an inefficient operation.
        """
        role_id = int(role['id'])

        groups_idx = self._get_role_as_group_idx(role_id)
        if groups_idx is None:
            return

        group = self.list.groups[groups_idx]
        group.position = role['position']

        # TODO: maybe this can be more efficient?
        # we could self.list.groups.insert... but I don't know.
        # I'm taking the safe route right now by using sorted()
        new_groups = sorted(self.list.groups,
                            key=lambda group: group.position)

        self.list.groups = new_groups

    async def role_update(self, role: dict):
        """Update a role.

        This function only takes care of updating
        any permission-related info, and removing
        the group if it lost the permissions to
        read the channel.
        """
        role_id = int(role['id'])

        group_idx = self._get_role_as_group_idx(role_id)
        if not group_idx:
            return

        group = self.list.groups[group_idx]
        group.permissions = Permissions(role['permissions'])

        await self._fetch_overwrites()

        # if the role can't read the channel anymore,
        # we have to delete it just like an actual role
        # deletion event.

        # role_delte will take care of sending the
        # respective GUILD_MEMBER_LIST_UPDATE events
        # down to the subscribers.
        if not self._can_read_chan(group):
            return await self.role_delete(role_id)

    async def role_delete(self, role_id: int):
        """Called when a role is deleted, so we should
        delete it off the list."""

        if not self.list:
            return

        # before we delete anything, we need to find the
        # states we'll resend the list info to.

        # find the item id for the group info
        role_item_index = index_by_func(
            lambda d: d.get('group', {}).get('id') == role_id,
            self.items
        )

        sess_ids_resync = self.get_subs(role_item_index)

        # remove the group info off the list
        groups_index = index_by_func(
            lambda group: group.gid == role_id,
            self.list.groups
        )

        if groups_index is not None:
            del self.list.groups[groups_index]
        else:
            log.warning('list unstable: {} not on group list', role_id)

        # then the state of it in the group_info list
        try:
            self.list.group_info.pop(role_id)
        except KeyError:
            log.warning('list unstable: {} not on group info', role_id)

        # now the data info
        try:
            self.list.data.pop(role_id)
        except KeyError:
            log.warning('list unstable: {} not in data dict', role_id)

        # and then overwrites.
        try:
            self.list.overwrites.pop(role_id)
        except KeyError:
            log.warning('list unstable: {} not in overwrites dict', role_id)

        # after removing, we do a resync with the
        # shards that had the group.

        for session_id in sess_ids_resync:
            # find the list range that the group was on
            # so we resync only the given range, instead
            # of the whole list state.
            ranges = self.state[session_id]

            try:
                # get the only range where the group is in
                role_range = next((r_min, r_max) for r_min, r_max in ranges
                                  if r_min < role_item_index < r_max)
            except StopIteration:
                continue

            # do resync-ing in the background
            self.loop.create_task(
                self.shard_query(session_id, role_range)
            )


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
        gml.unsub(session_id)

    async def dispatch(self, guild_id, event: str, *args, **kwargs):
        """Call a function specialized in handling the given event"""
        try:
            handler = getattr(self, f'_handle_{event}')
            await handler(guild_id, *args, **kwargs)
        except AttributeError:
            log.warning('unknown event: {}', event)
            return

    async def _call_all_lists(self, guild_id, method_str: str, *args):
        lists = self.get_gml_guild(guild_id)

        log.debug('calling method={} to all {} lists',
                  method, len(lists))

        for lazy_list in lists:
            method = getattr(lazy_list, method_str)
            await method(*args)

    async def _handle_new_role(self, guild_id: int, new_role: dict):
        """Handle the addition of a new group by dispatching it to
        the member lists."""
        await self._call_all_lists(guild_id, 'new_role', new_role)

    async def _handle_role_pos_upd(self, guild_id, role: dict):
        await self._call_all_lists(guild_id, 'role_pos_update', role)

    async def _handle_role_update(self, guild_id, role: dict):
        # handle name and hoist changes
        await self._call_all_lists(guild_id, 'role_update', role)

    async def _handle_role_delete(self, guild_id, role_id: int):
        await self._call_all_lists(guild_id, 'role_delete', role_id)
