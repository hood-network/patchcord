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
    GUILD_NEWS = 5
    NEWS_THREAD = 10
    PUBLIC_THREAD = 11
    PRIVATE_THREAD = 12


THREAD_TYPES = (
    ChannelType.NEWS_THREAD,
    ChannelType.PUBLIC_THREAD,
    ChannelType.PRIVATE_THREAD,
)


GUILD_CHANS = (
    ChannelType.GUILD_TEXT,
    ChannelType.GUILD_VOICE,
    ChannelType.GUILD_CATEGORY,
    ChannelType.GUILD_NEWS,
)


VOICE_CHANNELS = (ChannelType.DM, ChannelType.GUILD_VOICE, ChannelType.GROUP_DM)


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
    GUILD_BOOST = 8
    GUILD_BOOST_TIER_1 = 9
    GUILD_BOOST_TIER_2 = 10
    GUILD_BOOST_TIER_3 = 11
    CHANNEL_FOLLOW_ADD = 12
    GUILD_STREAM = 13
    GUILD_DISCOVERY_DISQUALIFIED = 14
    GUILD_DISCOVERY_REQUALIFIED = 15
    GUILD_DISCOVERY_GRACE_PERIOD_INITIAL_WARNING = 16
    GUILD_DISCOVERY_GRACE_PERIOD_FINAL_WARNING = 17
    THREAD_CREATED = 18
    REPLY = 19
    CHAT_INPUT_COMMAND = 20
    THREAD_STARTER_MESSAGE = 21
    GUILD_INVITE_REMINDER = 22
    CONTEXT_MENU_COMMAND = 23
    AUTO_MODERATION_ACTION = 24


class WebhookType(EasyEnum):
    INCOMING = 1
    FOLLOWER = 2
    APPLICATION = 3


SYS_MESSAGES = (
    MessageType.RECIPIENT_ADD,
    MessageType.RECIPIENT_REMOVE,
    MessageType.CALL,
    MessageType.CHANNEL_NAME_CHANGE,
    MessageType.CHANNEL_ICON_CHANGE,
    MessageType.CHANNEL_PINNED_MESSAGE,
    MessageType.GUILD_MEMBER_JOIN,
    MessageType.GUILD_BOOST,
    MessageType.GUILD_BOOST_TIER_1,
    MessageType.GUILD_BOOST_TIER_2,
    MessageType.GUILD_BOOST_TIER_3,
    MessageType.CHANNEL_FOLLOW_ADD,
    MessageType.GUILD_STREAM,
    MessageType.GUILD_DISCOVERY_DISQUALIFIED,
    MessageType.GUILD_DISCOVERY_REQUALIFIED,
    MessageType.GUILD_DISCOVERY_GRACE_PERIOD_INITIAL_WARNING,
    MessageType.GUILD_DISCOVERY_GRACE_PERIOD_FINAL_WARNING,
    MessageType.THREAD_CREATED,
    MessageType.THREAD_STARTER_MESSAGE,
    MessageType.GUILD_INVITE_REMINDER,
    MessageType.AUTO_MODERATION_ACTION,
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
    party_privacy_friends = 64
    party_privacy_voice_channel = 128
    embedded = 256


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

    team_user = 1024

    partner_or_verification_application = 2048
    system = 4096
    unread_urgent_system = 8192

    bug_hunter_2 = 16384

    underage_deleted = 32768
    verified_bot = 65536
    verified_developer = 131072
    certified_moderator = 262144

    http_interactions = 524288
    spammer = 1048576
    disable_premium = 2097152


class MessageFlags(Flags):
    """Message flags."""

    none = 0

    crossposted = 1 << 0
    is_crosspost = 1 << 1
    suppress_embeds = 1 << 2
    source_message_deleted = 1 << 3
    urgent = 1 << 4
    has_thread = 1 << 5
    ephemeral = 1 << 6
    loading = 1 << 7
    failed_to_mention_some_roles_in_thread = 1 << 8


class StatusType(EasyEnum):
    """All statuses there can be in a presence."""

    ONLINE = "online"
    DND = "dnd"
    IDLE = "idle"
    INVISIBLE = "invisible"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


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


class NSFWLevel(EasyEnum):
    """NSFW levels for guilds."""

    DEFAULT = 0
    EXPLICIT = 1
    SAFE = 2
    RESTRICTED = 3


class PremiumType:
    """Premium (Nitro) type."""

    TIER_0 = 0
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
    MESSAGE_CONTENT = 1 << 15

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
    "CHANNEL_PINS_UPDATE": (Intents.DIRECT_MESSAGES, Intents.GUILDS),
    "THREAD_CREATE": Intents.GUILDS,
    "THREAD_UPDATE": Intents.GUILDS,
    "THREAD_DELETE": Intents.GUILDS,
    "THREAD_LIST_SYNC": Intents.GUILDS,
    "THREAD_MEMBER_UPDATE": Intents.GUILDS,
    "THREAD_MEMBERS_UPDATE": Intents.GUILDS,
    "STAGE_INSTANCE_CREATE": Intents.GUILDS,
    "STAGE_INSTANCE_UPDATE": Intents.GUILDS,
    "STAGE_INSTANCE_DELETE": Intents.GUILDS,
    "GUILD_MEMBER_ADD": Intents.GUILD_MEMBERS,
    "GUILD_MEMBER_UPDATE": Intents.GUILD_MEMBERS,
    "GUILD_MEMBER_REMOVE": Intents.GUILD_MEMBERS,
    "THREAD_MEMBERS_UPDATE": Intents.GUILD_MEMBERS,
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
    # Intents vary depending on the event context
    "MESSAGE_CREATE": (Intents.DIRECT_MESSAGES, Intents.GUILD_MESSAGES),
    "MESSAGE_UPDATE": (Intents.DIRECT_MESSAGES, Intents.GUILD_MESSAGES),
    "MESSAGE_DELETE": (Intents.DIRECT_MESSAGES, Intents.GUILD_MESSAGES),
    "MESSAGE_DELETE_BULK": (Intents.DIRECT_MESSAGES, Intents.GUILD_MESSAGES),
    "MESSAGE_REACTION_ADD": (
        Intents.DIRECT_MESSAGE_REACTIONS,
        Intents.GUILD_MESSAGE_REACTIONS,
    ),
    "MESSAGE_REACTION_REMOVE": (
        Intents.DIRECT_MESSAGE_REACTIONS,
        Intents.GUILD_MESSAGE_REACTIONS,
    ),
    "MESSAGE_REACTION_REMOVE_ALL": (
        Intents.DIRECT_MESSAGE_REACTIONS,
        Intents.GUILD_MESSAGE_REACTIONS,
    ),
    "MESSAGE_REACTION_REMOVE_EMOJI": (
        Intents.DIRECT_MESSAGE_REACTIONS,
        Intents.GUILD_MESSAGE_REACTIONS,
    ),
    "TYPING_START": (Intents.DIRECT_MESSAGE_TYPING, Intents.GUILD_MESSAGE_TYPING),
}
