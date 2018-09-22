import ctypes

from enum import Enum


class EasyEnum(Enum):
    @classmethod
    def values(cls):
        return [v.value for v in cls.__members__.values()]


class ChannelType(EasyEnum):
    GUILD_TEXT = 0
    DM = 1
    GUILD_VOICE = 2
    GROUP_DM = 3
    GUILD_CATEGORY = 4


class ActivityType(EasyEnum):
    PLAYING = 0
    STREAMING = 1
    LISTENING = 2


class MessageType(EasyEnum):
    DEFAULT = 0
    RECIPIENT_ADD = 1
    RECIPIENT_REMOVE = 2
    CALL = 3
    CHANNEL_NAME_CHANGE = 4
    CHANNEL_ICON_CHANGE = 5
    CHANNEL_PINNED_MESSAGE = 6
    GUILD_MEMBER_JOIN = 7


class MessageActivityType(EasyEnum):
    JOIN = 1
    SPECTATE = 2
    LISTEN = 3
    JOIN_REQUEST = 5


uint8 = ctypes.c_uint8


# use ctypes to interpret the bits in activity flags
class ActivityFlagsBits(ctypes.LittleEndianStructure):
    _fields_ = [
        ('instance', uint8, 1),
        ('join', uint8, 1),
        ('spectate', uint8, 1),
        ('join_request', uint8, 1),
        ('sync', uint8, 1),
        ('play', uint8, 1),
    ]


class ActivityFlags(ctypes.Union):
    _anonymous_ = ('bit',)

    _fields_ = [
        ('bit', ActivityFlagsBits),
        ('as_byte', uint8),
    ]


class StatusType(EasyEnum):
    ONLINE = 'online'
    DND = 'dnd'
    IDLE = 'idle'
    INVISIBLE = 'invisible'
    OFFLINE = 'offline'


class ExplicitFilter(EasyEnum):
    EDGE = 0
    FRIENDS = 1
    SAFE = 2
