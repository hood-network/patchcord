"""

Litecord
Copyright (C) 2018-2021  Luna Mendes and Litecord Contributors

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
from typing import List, Any
from enum import Enum, IntEnum, IntFlag


class EasyEnum(Enum):
    """Wrapper around the enum class for convenience."""

    @classmethod
    def values(cls) -> List[Any]:
        """Return list of values for the given enum."""
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
        # get only the members that represent a field
        cls._attrs = inspect.getmembers(cls, lambda x: isinstance(x, int))

    @classmethod
    def from_int(cls, value: int):
        """Create a Flags from a given int value."""
        res = Flags()
        setattr(res, "value", value)

        for attr, val in cls._attrs:
            has_attr = (value & val) == val
            # set attributes dynamically
            setattr(res, f"is_{attr.lower()}", has_attr)

        return res


class ChannelType(EasyEnum):
    GUILD_TEXT = 0
    DM = 1
    GUILD_VOICE = 2
    GROUP_DM = 3
    GUILD_CATEGORY = 4


GUILD_CHANS = (
    ChannelType.GUILD_TEXT,
    ChannelType.GUILD_VOICE,
    ChannelType.GUILD_CATEGORY,
)


VOICE_CHANNELS = (ChannelType.DM, ChannelType.GUILD_VOICE, ChannelType.GUILD_CATEGORY)


class ActivityType(EasyEnum):
    PLAYING = 0
    STREAMING = 1
    LISTENING = 2
    WATCHING = 3
    CUSTOM = 4


class MessageType(EasyEnum):
    DEFAULT = 0
    RECIPIENT_ADD = 1
    RECIPIENT_REMOVE = 2
    CALL = 3
    CHANNEL_NAME_CHANGE = 4
    CHANNEL_ICON_CHANGE = 5
    CHANNEL_PINNED_MESSAGE = 6
    GUILD_MEMBER_JOIN = 7


SYS_MESSAGES = (
    MessageType.RECIPIENT_ADD,
    MessageType.RECIPIENT_REMOVE,
    MessageType.CALL,
    MessageType.CHANNEL_NAME_CHANGE,
    MessageType.CHANNEL_ICON_CHANGE,
    MessageType.CHANNEL_PINNED_MESSAGE,
    MessageType.GUILD_MEMBER_JOIN,
)


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
    bug_hunter_1 = 8
    mfa_sms = 16
    premium_dismissed = 32

    hsquad_house_1 = 64
    hsquad_house_2 = 128
    hsquad_house_3 = 256

    premium_early = 512

    unread_system = 4096
    unread_urgent_system = 8192

    bug_hunter_2 = 16384

    underage_deleted = 1 << 15
    verified_bot = 1 << 16
    verified_developer = 1 << 17
    certified_moderator = 1 << 18


class MessageFlags(Flags):
    """Message flags."""

    none = 0

    crossposted = 1 << 0
    is_crosspost = 1 << 1
    suppress_embeds = 1 << 2


class StatusType(EasyEnum):
    """All statuses there can be in a presence."""

    ONLINE = "online"
    DND = "dnd"
    IDLE = "idle"
    INVISIBLE = "invisible"
    OFFLINE = "offline"


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
    """Message notifications"""

    ALL = 0
    MENTIONS = 1
    NOTHING = 2


class PremiumType:
    """Premium (Nitro) type."""

    TIER_1 = 1
    TIER_2 = 2
    NONE = None


class Feature(EasyEnum):
    """Guild features."""

    invite_splash = "INVITE_SPLASH"
    vip = "VIP_REGIONS"
    vanity = "VANITY_URL"
    emoji = "MORE_EMOJI"
    verified = "VERIFIED"
    public = "PUBLIC"

    # unknown
    commerce = "COMMERCE"
    news = "NEWS"


class Intents(IntFlag):
    GUILDS = 1 << 0
    GUILD_MEMBERS = 1 << 1
    GUILD_BANS = 1 << 2
    GUILD_EMOJIS = 1 << 3
    GUILD_INTEGRATIONS = 1 << 4
    GUILD_WEBHOOKS = 1 << 5
    GUILD_INVITES = 1 << 6
    GUILD_VOICE_STATES = 1 << 7
    GUILD_PRESENCES = 1 << 8
    GUILD_MESSAGES = 1 << 9
    GUILD_MESSAGE_REACTIONS = 1 << 10
    GUILD_MESSAGE_TYPING = 1 << 11
    DIRECT_MESSAGES = 1 << 12
    DIRECT_MESSAGE_REACTIONS = 1 << 13
    DIRECT_MESSAGE_TYPING = 1 << 14

    @classmethod
    def default(cls):
        return cls(-1)


EVENTS_TO_INTENTS = {
    "GUILD_CREATE": Intents.GUILDS,
    "GUILD_UPDATE": Intents.GUILDS,
    "GUILD_DELETE": Intents.GUILDS,
    "GUILD_ROLE_CREATE": Intents.GUILDS,
    "GUILD_ROLE_UPDATE": Intents.GUILDS,
    "GUILD_ROLE_DELETE": Intents.GUILDS,
    "CHANNEL_CREATE": Intents.GUILDS,
    "CHANNEL_UPDATE": Intents.GUILDS,
    "CHANNEL_DELETE": Intents.GUILDS,
    "CHANNEL_PINS_UPDATE": Intents.GUILDS,
    # --- threads not supported --
    "THREAD_CREATE": Intents.GUILDS,
    "THREAD_UPDATE": Intents.GUILDS,
    "THREAD_DELETE": Intents.GUILDS,
    "THREAD_LIST_SYNC": Intents.GUILDS,
    "THREAD_MEMBER_UPDATE": Intents.GUILDS,
    "THREAD_MEMBERS_UPDATE": Intents.GUILDS,
    # --- stages not supported --
    "STAGE_INSTANCE_CREATE": Intents.GUILDS,
    "STAGE_INSTANCE_UPDATE": Intents.GUILDS,
    "STAGE_INSTANCE_DELETE": Intents.GUILDS,
    "GUILD_MEMBER_ADD": Intents.GUILD_MEMBERS,
    "GUILD_MEMBER_UPDATE": Intents.GUILD_MEMBERS,
    "GUILD_MEMBER_REMOVE": Intents.GUILD_MEMBERS,
    # --- threads not supported --
    "THREAD_MEMBERS_UPDATE ": Intents.GUILD_MEMBERS,
    "GUILD_BAN_ADD": Intents.GUILD_BANS,
    "GUILD_BAN_REMOVE": Intents.GUILD_BANS,
    "GUILD_EMOJIS_UPDATE": Intents.GUILD_EMOJIS,
    "GUILD_INTEGRATIONS_UPDATE": Intents.GUILD_INTEGRATIONS,
    "INTEGRATION_CREATE": Intents.GUILD_INTEGRATIONS,
    "INTEGRATION_UPDATE": Intents.GUILD_INTEGRATIONS,
    "INTEGRATION_DELETE": Intents.GUILD_INTEGRATIONS,
    "WEBHOOKS_UPDATE": Intents.GUILD_WEBHOOKS,
    "INVITE_CREATE": Intents.GUILD_INVITES,
    "INVITE_DELETE": Intents.GUILD_INVITES,
    "VOICE_STATE_UPDATE": Intents.GUILD_VOICE_STATES,
    "PRESENCE_UPDATE": Intents.GUILD_PRESENCES,
    "MESSAGE_CREATE": Intents.GUILD_MESSAGES,
    "MESSAGE_UPDATE": Intents.GUILD_MESSAGES,
    "MESSAGE_DELETE": Intents.GUILD_MESSAGES,
    "MESSAGE_DELETE_BULK": Intents.GUILD_MESSAGES,
    "MESSAGE_REACTION_ADD": Intents.GUILD_MESSAGE_REACTIONS,
    "MESSAGE_REACTION_REMOVE": Intents.GUILD_MESSAGE_REACTIONS,
    "MESSAGE_REACTION_REMOVE_ALL": Intents.GUILD_MESSAGE_REACTIONS,
    "MESSAGE_REACTION_REMOVE_EMOJI": Intents.GUILD_MESSAGE_REACTIONS,
    "TYPING_START": Intents.GUILD_MESSAGE_TYPING,
}
