import ctypes

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
