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


GUILD_CHANS = (ChannelType.GUILD_TEXT,
               ChannelType.GUILD_VOICE,
               ChannelType.GUILD_CATEGORY)


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


class ActivityFlags:
    instance = 1
    join = 2
    spectate = 4
    join_request = 8
    sync = 16
    play = 32


class UserFlags:
    staff = 1
    partner = 2
    hypesquad = 4
    bug_hunter = 8
    mfa_sms = 16
    premium_dismissed = 32

    hsquad_house_1 = 64
    hsquad_house_2 = 128
    hsquad_house_3 = 256

    premium_early = 512


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


class RelationshipType(EasyEnum):
    FRIEND = 1
    BLOCK = 2
    INCOMING = 3
    OUTGOING = 4
