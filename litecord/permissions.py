import ctypes

from quart import current_app as app, request

# so we don't keep repeating the same
# type for all the fields
_i = ctypes.c_uint8

class _RawPermsBits(ctypes.LittleEndianStructure):
    """raw bitfield for discord's permission number."""
    _fields_ = [
        ('create_invites', _i, 1),
        ('kick_members', _i, 1),
        ('ban_members', _i, 1),
        ('administrator', _i, 1),
        ('manage_channels', _i, 1),
        ('manage_guild', _i, 1),
        ('add_reactions', _i, 1),
        ('view_audit_log', _i, 1),
        ('priority_speaker', _i, 1),
        ('_unused1', _i, 1),
        ('read_messages', _i, 1),
        ('send_messages', _i, 1),
        ('send_tts', _i, 1),
        ('manage_messages', _i, 1),
        ('embed_links', _i, 1),
        ('attach_files', _i, 1),
        ('read_history', _i, 1),
        ('mention_everyone', _i, 1),
        ('external_emojis', _i, 1),
        ('_unused2', _i, 1),
        ('connect', _i, 1),
        ('speak', _i, 1),
        ('mute_members', _i, 1),
        ('deafen_members', _i, 1),
        ('move_members', _i, 1),
        ('use_voice_activation', _i, 1),
        ('change_nickname', _i, 1),
        ('manage_nicknames', _i, 1),
        ('manage_roles', _i, 1),
        ('manage_webhooks', _i, 1),
        ('manage_emojis', _i, 1),
    ]


class Permissions(ctypes.Union):
    _fields_ = [
        ('bits', _RawPermsBits),
        ('binary', ctypes.c_uint64),
    ]

    def __init__(self, val: int):
        self.binary = val

    def __int__(self):
        return self.binary

    def numby(self):
        return self.binary


ALL_PERMISSIONS = Permissions(0b01111111111101111111110111111111)


async def base_permissions(member_id, guild_id) -> Permissions:
    """Compute the base permissions for a given user.

    Base permissions are
        (permissions from @everyone role) +
        (permissions from any other role the member has)

    This will give ALL_PERMISSIONS if base permissions
    has the Administrator bit set.
    """
    owner_id = await app.db.fetchval("""
    SELECT owner_id
    FROM guilds
    WHERE id = $1
    """, guild_id)

    if owner_id == member_id:
        return ALL_PERMISSIONS

    # get permissions for @everyone
    everyone_perms = await app.db.fetchval("""
    SELECT permissions
    FROM roles
    WHERE guild_id = $1
    """, guild_id)

    permissions = everyone_perms

    role_perms = await app.db.fetch("""
    SELECT permissions
    FROM roles
    WHERE guild_id = $1 AND user_id = $2
    """, guild_id, member_id)

    for perm_num in role_perms:
        permissions.binary |= perm_num

    if permissions.bits.administrator:
        return ALL_PERMISSIONS

    return permissions


def _mix(perms: Permissions, overwrite: dict) -> Permissions:
    # we make a copy of the binary representation
    # so we don't modify the old perms in-place
    # which could be an unwanted side-effect
    result = perms.binary

    # negate the permissions that are denied
    result &= ~overwrite['deny']

    # combine the permissions that are allowed
    result |= overwrite['allow']

    return Permissions(result)


def _overwrite_mix(perms: Permissions, overwrites: dict,
                   target_id: int) -> Permissions:
    overwrite = overwrites.get(target_id)

    if overwrite:
        # only mix if overwrite found
        return _mix(perms, overwrite)

    return perms


async def compute_overwrites(base_perms, user_id, channel_id: int,
                             guild_id: int = None):
    """Compute the permissions in the context of a channel."""

    if base_perms.bits.administrator:
        return ALL_PERMISSIONS

    perms = base_perms

    # list of overwrites
    overwrites = await app.storage.chan_overwrites(channel_id)

    if not guild_id:
        guild_id = await app.storage.guild_from_channel(channel_id)

    # make it a map for better usage
    overwrites = {o['id']: o for o in overwrites}

    perms = _overwrite_mix(perms, overwrites, guild_id)

    # apply role specific overwrites
    allow, deny = 0, 0

    # fetch roles from user and convert to int
    role_ids = await app.storage.get_member_role_ids(guild_id, user_id)
    role_ids = map(int, role_ids)

    # make the allow and deny binaries
    for role_id in role_ids:
        overwrite = overwrites.get(role_id)
        if overwrite:
            allow |= overwrite['allow']
            deny |= overwrite['deny']

    # final step for roles: mix
    perms = _mix(perms, {
        'allow': allow,
        'deny': deny
    })

    # apply member specific overwrites
    perms = _overwrite_mix(perms, overwrites, user_id)

    return perms


async def get_permissions(member_id, channel_id):
    """Get all the permissions for a user in a channel."""
    guild_id = await app.storage.guild_from_channel(channel_id)
    base_perms = await base_permissions(member_id, guild_id)

    return await compute_overwrites(base_perms, member_id,
                                    channel_id, guild_id)
