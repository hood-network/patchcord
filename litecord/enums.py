"""

Litecord
Copyright (C) 2018  Luna Mendes

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""

import inspect
from enum import Enum, IntEnum


class EasyEnum(Enum):
    @classmethod
    def values(cls):
        return [v.value for v in cls.__members__.values()]


class Flags:
    """Construct a class that represents a bitfield.
    
    You can use it like this:
        >>> class MyField(Flags):
                field_1 = 1
                field_2 = 2
                field_3 = 4
        >>> i1 = MyField.from_int(1)
        >>> i1.is_field_1
        True
        >>> i1.is_field_2
        False
        >>> i2 = MyField.from_int(3)
        >>> i2.is_field_1
        True
        >>> i2.is_field_2
        True
        >>> i2.is_field_3
        False
    """
    def __init_subclass__(cls, **_kwargs):
        attrs = inspect.getmembers(cls, lambda x: not inspect.isroutine(x))

        def _make_int(value):
            res = Flags()

            for attr, val in attrs:
                # get only the ones that represent a field in the
                # number's bits
                if not isinstance(val, int):
                    continue

                has_attr = (value & val) == val

                # set each attribute
                setattr(res, f'is_{attr}', has_attr)

            return res

        cls.from_int = _make_int


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
    WATCHING = 3


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


class ActivityFlags(Flags):
    """Activity flags. Make up the ActivityType
    in a message.

    Only related to rich presence.
    """
    instance = 1
    join = 2
    spectate = 4
    join_request = 8
    sync = 16
    play = 32


class UserFlags(Flags):
    """User flags.

    Used by the client to show badges.
    """
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
    """All statuses there can be in a presence."""
    ONLINE = 'online'
    DND = 'dnd'
    IDLE = 'idle'
    INVISIBLE = 'invisible'
    OFFLINE = 'offline'


class ExplicitFilter(EasyEnum):
    """Explicit filter for users' messages.

    Also applies to guilds.
    """
    EDGE = 0
    FRIENDS = 1
    SAFE = 2


class VerificationLevel(IntEnum):
    """Verification level for guilds."""
    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3

    # require phone check
    EXTREME = 4


class RelationshipType(EasyEnum):
    """Relationship types between users."""
    FRIEND = 1
    BLOCK = 2
    INCOMING = 3
    OUTGOING = 4


class MessageNotifications(EasyEnum):
    ALL = 0
    MENTIONS = 1
    NOTHING = 2


class PremiumType:
    TIER_1 = 1
    TIER_2 = 2
    NONE = None
