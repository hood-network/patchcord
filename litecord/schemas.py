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

import re

# from datetime import datetime
from typing import Union, Dict, List, Optional

from cerberus import Validator
from logbook import Logger
from quart import current_app as app

from .errors import BadRequest
from .permissions import Permissions
from .types import Color
from .enums import (
    ActivityType,
    StatusType,
    ExplicitFilter,
    RelationshipType,
    MessageNotifications,
    ChannelType,
    VerificationLevel,
)

from litecord.embed.schemas import EMBED_OBJECT, EmbedURL

log = Logger(__name__)

# TODO use any char instead of english lol
USERNAME_REGEX = re.compile(r"^[a-zA-Z0-9_ ]{2,30}$", re.A)

# TODO better email regex maybe
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", re.A)
DATA_REGEX = re.compile(r"data\:image/(png|jpeg|gif);base64,(.+)", re.A)


# collection of regexes
USER_MENTION = re.compile(r"<@!?(\d+)>", re.A | re.M)
CHAN_MENTION = re.compile(r"<#(\d+)>", re.A | re.M)
ROLE_MENTION = re.compile(r"<@&(\d+)>", re.A | re.M)
EMOJO_MENTION = re.compile(r"<:(\.+):(\d+)>", re.A | re.M)
ANIMOJI_MENTION = re.compile(r"<a:(\.+):(\d+)>", re.A | re.M)


def _in_enum(enum, value) -> bool:
    """Return if a given value is in the enum."""
    try:
        enum(value)
        return True
    except ValueError:
        return False


class LitecordValidator(Validator):
    """Main validator class for Litecord, containing custom types."""

    def _validate_type_username(self, value: str) -> bool:
        """Validate against the username regex."""
        return bool(USERNAME_REGEX.match(value))

    def _validate_type_password(self, value: str) -> bool:
        """Validate a password. Max 1024 chars.

        The valid password length on Discord's client might be different.
        """
        return 8 <= len(value) <= 1024

    def _validate_type_email(self, value: str) -> bool:
        """Validate against the email regex."""
        return bool(EMAIL_REGEX.match(value)) and len(value) < 256

    def _validate_type_b64_icon(self, value: str) -> bool:
        return bool(DATA_REGEX.match(value))

    def _validate_type_discriminator(self, value: str) -> bool:
        """Discriminators are numbers in the API
        that can go from 0 to 9999.
        """
        try:
            discrim = int(value)
        except (TypeError, ValueError):
            return False

        return 0 < discrim <= 9999

    def _validate_type_snowflake(self, value: str) -> bool:
        try:
            int(value)
            return True
        except ValueError:
            return False

    def _validate_type_voice_region(self, value: str) -> bool:
        # NOTE: when this code is being ran, there is a small chance the
        # app context injected by quart still exists
        return value.lower() in app.voice.lvsp.regions.keys()

    def _validate_type_verification_level(self, value: int) -> bool:
        return _in_enum(VerificationLevel, value)

    def _validate_type_activity_type(self, value: int) -> bool:
        return value in ActivityType.values()

    def _validate_type_channel_type(self, value: int) -> bool:
        return value in ChannelType.values()

    def _validate_type_status_external(self, value: str) -> bool:
        statuses = StatusType.values()
        return value in statuses

    def _validate_type_explicit(self, value: str) -> bool:
        try:
            val = int(value)
        except (TypeError, ValueError):
            return False

        return val in ExplicitFilter.values()

    def _validate_type_rel_type(self, value: str) -> bool:
        try:
            val = int(value)
        except (TypeError, ValueError):
            return False

        # nobody is allowed to use the INCOMING and OUTGOING rel types
        return val in (RelationshipType.FRIEND.value, RelationshipType.BLOCK.value)

    def _validate_type_msg_notifications(self, value: str):
        try:
            val = int(value)
        except (TypeError, ValueError):
            return False

        return val in MessageNotifications.values()

    def _validate_type_guild_name(self, value: str) -> bool:
        return 2 <= len(value) <= 100

    def _validate_type_role_name(self, value: str) -> bool:
        return 1 <= len(value) <= 100

    def _validate_type_channel_name(self, value: str) -> bool:
        # for now, we'll use the same validation for guild_name
        return self._validate_type_guild_name(value)

    def _validate_type_theme(self, value: str) -> bool:
        return value in ["light", "dark"]

    def _validate_type_nickname(self, value: str) -> bool:
        return isinstance(value, str) and (len(value) < 32)

    def _validate_type_rgb_int_color(self, value: int) -> bool:
        return isinstance(value, int) and value > 0 and value < 0xFFFFFF


def validate(
    reqjson: Optional[Union[Dict, List]],
    schema: Dict,
) -> Dict:
    """Validate the given user-given data against a schema, giving the
    "correct" version of the document, with all defaults applied.

    Raises BadRequest error when the validation fails.

    Parameters
    ----------
    reqjson:
        The input data
    schema:
        The schema to validate reqjson against
    """
    validator = LitecordValidator(schema)

    if reqjson is None:
        raise BadRequest("No JSON provided")

    try:
        valid = validator.validate(reqjson)
    except Exception:
        log.exception("Error while validating")
        raise Exception(f"Error while validating: {reqjson}")

    if not valid:
        errs = validator.errors
        log.warning("Error validating doc {!r}: {!r}", reqjson, errs)
        raise BadRequest("bad payload", errs)

    return validator.document


REGISTER = {
    "username": {"type": "username", "required": True},
    "email": {"type": "email", "required": False},
    "password": {"type": "password", "required": False},
    # invite stands for a guild invite, not an instance invite (that's on
    # the register_with_invite handler).
    "invite": {"type": "string", "required": False, "nullable": True},
    # following fields only sent by official client, unused by us
    "fingerprint": {"type": "string", "required": False, "nullable": True},
    "captcha_key": {"type": "string", "required": False, "nullable": True},
    "gift_code_sku_id": {"type": "string", "required": False, "nullable": True},
    "consent": {"type": "boolean", "required": False},
    "date_of_birth": {"type": "string", "required": False, "nullable": True},
}

# only used by us, not discord, hence 'invcode' (to separate from discord)
REGISTER_WITH_INVITE = {**REGISTER, **{"invcode": {"type": "string", "required": True}}}


USER_UPDATE = {
    "username": {
        "type": "username",
        "minlength": 2,
        "maxlength": 30,
        "required": False,
    },
    "discriminator": {"type": "discriminator", "required": False, "nullable": True},
    "password": {"type": "password", "required": False},
    "new_password": {
        "type": "password",
        "required": False,
        "dependencies": "password",
        "nullable": True,
    },
    "email": {"type": "email", "required": False, "dependencies": "password"},
    "avatar": {
        # can be both b64_icon or string (just the hash)
        "type": "string",
        "required": False,
        "nullable": True,
    },
    "bio": {
        "type": "string",
        "required": False,
        "nullable": False,
    },
    "accent_color": {
        "type": "rgb_int_color",
        "required": False,
        "nullable": True,
    },
}

PARTIAL_ROLE_GUILD_CREATE = {
    "type": "dict",
    "schema": {
        "name": {"type": "role_name"},
        "color": {"type": "number", "default": 0},
        "hoist": {"type": "boolean", "default": False},
        # NOTE: no position on partial role (on guild create)
        "permissions": {"coerce": Permissions, "required": False},
        "mentionable": {"type": "boolean", "default": False},
    },
}

PARTIAL_CHANNEL_GUILD_CREATE = {
    "type": "dict",
    "schema": {"name": {"type": "channel_name"}, "type": {"type": "channel_type"}},
}

GUILD_CREATE = {
    "name": {"type": "guild_name"},
    "region": {"type": "voice_region", "nullable": True},
    "icon": {"type": "b64_icon", "required": False, "nullable": True},
    "verification_level": {"type": "verification_level", "default": 0},
    "default_message_notifications": {"type": "msg_notifications", "default": 0},
    "explicit_content_filter": {"type": "explicit", "default": 0},
    "roles": {"type": "list", "required": False, "schema": PARTIAL_ROLE_GUILD_CREATE},
    "channels": {"type": "list", "default": [], "schema": PARTIAL_CHANNEL_GUILD_CREATE},
    # not supported
    "system_channel_id": {"coerce": int, "required": False, "nullable": True},
    "guild_template_code": {
        "type": "string",
        "required": False,
    },
}


GUILD_UPDATE = {
    "name": {"type": "guild_name", "required": False},
    "region": {"type": "voice_region", "required": False, "nullable": True},
    # all three can have hashes
    "icon": {"type": "string", "required": False, "nullable": True},
    "banner": {"type": "string", "required": False, "nullable": True},
    "splash": {"type": "string", "required": False, "nullable": True},
    "description": {
        "type": "string",
        "required": False,
        "minlength": 1,
        "maxlength": 120,
        "nullable": True,
    },
    "verification_level": {"type": "verification_level", "required": False},
    "default_message_notifications": {"type": "msg_notifications", "required": False},
    "explicit_content_filter": {"type": "explicit", "required": False},
    "afk_channel_id": {
        "type": "snowflake",
        "coerce": int,
        "required": False,
        "nullable": True,
    },
    "afk_timeout": {"type": "number", "required": False},
    "owner_id": {"type": "snowflake", "coerce": int, "required": False},
    "system_channel_id": {
        "type": "snowflake",
        "coerce": int,
        "required": False,
        "nullable": True,
    },
    "features": {"type": "list", "required": False, "schema": {"type": "string"}},
    "rules_channel_id": {
        "type": "snowflake",
        "coerce": int,
        "required": False,
        "nullable": True,
    },
    "public_updates_channel_id": {
        "type": "snowflake",
        "coerce": int,
        "required": False,
        "nullable": True,
    },
    "preferred_locale": {"type": "string", "required": False, "nullable": True},
    "discovery_splash": {"type": "string", "required": False, "nullable": True},
}


CHAN_OVERWRITE = {
    "id": {"coerce": int},
    "type": {"type": "string", "allowed": ["role", "member"]},
    "allow": {"coerce": Permissions},
    "deny": {"coerce": Permissions},
}


CHAN_CREATE = {
    "name": {"type": "string", "minlength": 1, "maxlength": 100, "required": True},
    "type": {"type": "channel_type", "default": ChannelType.GUILD_TEXT.value},
    "position": {"coerce": int, "required": False},
    "topic": {"type": "string", "minlength": 0, "maxlength": 1024, "required": False},
    "nsfw": {"type": "boolean", "required": False},
    "rate_limit_per_user": {"coerce": int, "min": 0, "max": 120, "required": False},
    "bitrate": {
        "coerce": int,
        "min": 8000,
        # NOTE: 'max' is 96000 for non-vip guilds
        "max": 128000,
        "required": False,
    },
    "user_limit": {
        # user_limit being 0 means infinite.
        "coerce": int,
        "min": 0,
        "max": 99,
        "required": False,
    },
    "permission_overwrites": {
        "type": "list",
        "schema": {"type": "dict", "schema": CHAN_OVERWRITE},
        "required": False,
    },
    "parent_id": {"coerce": int, "required": False, "nullable": True},
}


CHAN_UPDATE = {
    **CHAN_CREATE,
    **{"name": {"type": "string", "minlength": 1, "maxlength": 100, "required": False}},
}


ROLE_CREATE = {
    "name": {"type": "string", "default": "new role"},
    "permissions": {"coerce": Permissions, "nullable": True},
    "color": {"coerce": Color, "default": 0},
    "hoist": {"type": "boolean", "default": False},
    "mentionable": {"type": "boolean", "default": False},
}

ROLE_UPDATE = {
    "name": {"type": "string", "required": False},
    "permissions": {"coerce": Permissions, "required": False},
    "color": {"coerce": Color, "required": False},
    "hoist": {"type": "boolean", "required": False},
    "mentionable": {"type": "boolean", "required": False},
}


ROLE_UPDATE_POSITION = {
    "roles": {
        "type": "list",
        "schema": {
            "type": "dict",
            "schema": {"id": {"coerce": int}, "position": {"coerce": int}},
        },
    }
}


MEMBER_UPDATE = {
    "nick": {"type": "nickname", "required": False},
    "roles": {"type": "list", "required": False, "schema": {"coerce": int}},
    "mute": {"type": "boolean", "required": False},
    "deaf": {"type": "boolean", "required": False},
    "channel_id": {"type": "snowflake", "required": False},
}


# NOTE: things such as payload_json are parsed at the handler
# for creating a message.
MESSAGE_CREATE = {
    "content": {"type": "string", "minlength": 0, "maxlength": 2000},
    "nonce": {"type": "snowflake", "required": False},
    "tts": {"type": "boolean", "required": False},
    "embed": {
        "type": "dict",
        "schema": EMBED_OBJECT,
        "required": False,
        "nullable": True,
    },
    "message_reference": {
        "type": "dict",
        "required": False,
        "nullable": True,
        "schema": {
            "guild_id": {"type": "string", "required": False},
            "channel_id": {"type": "string", "required": True},
            "message_id": {"type": "string", "required": True},
        },
    },
    "allowed_mentions": {
        "type": "dict",
        "required": False,
        "nullable": True,
        "schema": {
            "parse": {"type": "list", "required": False},
            "replied_user": {"type": "boolean", "required": False},
        },
    },
}


INVITE = {
    # max_age in seconds
    # 0 for infinite
    "max_age": {
        "type": "number",
        "min": 0,
        "max": 666666,  # TODO find correct max value
        # a day
        "default": 86400,
    },
    # max invite uses
    "max_uses": {
        "type": "number",
        "min": 0,
        # idk
        "max": 1000,
        # default infinite
        "default": 0,
    },
    "temporary": {"type": "boolean", "required": False, "default": False},
    "unique": {"type": "boolean", "required": False, "default": True},
    "validate": {
        "type": "string",
        "required": False,
        "nullable": True,
    },  # discord client sends invite code there
    # sent by official client, unknown purpose
    "target_type": {"type": "string", "required": False, "nullable": True},
    "target_user_id": {"type": "snowflake", "required": False, "nullable": True},
    "target_user_type": {"type": "number", "required": False, "nullable": True},
}

USER_SETTINGS = {
    "afk_timeout": {"type": "number", "required": False, "min": 0, "max": 3000},
    "animate_emoji": {"type": "boolean", "required": False},
    "convert_emoticons": {"type": "boolean", "required": False},
    "default_guilds_restricted": {"type": "boolean", "required": False},
    "detect_platform_accounts": {"type": "boolean", "required": False},
    "developer_mode": {"type": "boolean", "required": False},
    "disable_games_tab": {"type": "boolean", "required": False},
    "enable_tts_command": {"type": "boolean", "required": False},
    "explicit_content_filter": {"type": "explicit", "required": False},
    "friend_source": {
        "type": "dict",
        "required": False,
        "schema": {
            "all": {"type": "boolean", "required": False},
            "mutual_guilds": {"type": "boolean", "required": False},
            "mutual_friends": {"type": "boolean", "required": False},
        },
    },
    "guild_positions": {
        "type": "list",
        "required": False,
        "schema": {"type": "snowflake"},
    },
    "restricted_guilds": {
        "type": "list",
        "required": False,
        "schema": {"type": "snowflake"},
    },
    "gif_auto_play": {"type": "boolean", "required": False},
    "inline_attachment_media": {"type": "boolean", "required": False},
    "inline_embed_media": {"type": "boolean", "required": False},
    "message_display_compact": {"type": "boolean", "required": False},
    "render_embeds": {"type": "boolean", "required": False},
    "render_reactions": {"type": "boolean", "required": False},
    "show_current_game": {"type": "boolean", "required": False},
    "timezone_offset": {"type": "number", "required": False},
    "status": {"type": "status_external", "required": False},
    "theme": {"type": "theme", "required": False},
    "custom_status": {
        "type": "dict",
        "required": False,
        "nullable": True,
        "schema": {
            "emoji_id": {"coerce": int, "nullable": True},
            "emoji_name": {"type": "string", "nullable": True},
            # discord's timestamps dont seem to work well with
            # datetime.fromisoformat, so for now, we trust the client
            "expires_at": {"type": "string", "nullable": True},
            "text": {"type": "string", "nullable": True},
        },
    },
}

RELATIONSHIP = {
    "type": {
        "type": "rel_type",
        "required": False,
        "default": RelationshipType.FRIEND.value,
    }
}

CREATE_DM = {"recipient_id": {"type": "snowflake", "required": True}}

CREATE_GROUP_DM = {
    "recipient_id": {"type": "list", "required": True, "schema": {"type": "snowflake"}}
}

CREATE_GROUP_DM_V9 = {
    "recipients": {"type": "list", "required": True, "schema": {"type": "snowflake"}}
}

GROUP_DM_UPDATE = {
    "name": {"type": "guild_name", "required": False},
    "icon": {"type": "b64_icon", "required": False, "nullable": True},
}

SPECIFIC_FRIEND = {
    "username": {"type": "username"},
    "discriminator": {"type": "discriminator"},
}

GUILD_SETTINGS_CHAN_OVERRIDE = {
    "type": "dict",
    "schema": {
        "muted": {"type": "boolean", "required": False},
        "message_notifications": {"type": "msg_notifications", "required": False},
    },
}

GUILD_SETTINGS = {
    "channel_overrides": {
        "type": "dict",
        "valueschema": GUILD_SETTINGS_CHAN_OVERRIDE,
        "keyschema": {"type": "snowflake"},
        "required": False,
    },
    "suppress_everyone": {"type": "boolean", "required": False},
    "muted": {"type": "boolean", "required": False},
    "mobile_push": {"type": "boolean", "required": False},
    "message_notifications": {"type": "msg_notifications", "required": False},
}

GUILD_PRUNE = {
    "days": {"type": "number", "coerce": int, "min": 1, "max": 30, "default": 7},
    "compute_prune_count": {"type": "string", "default": "true"},
}

NEW_EMOJI = {
    "name": {"type": "string", "minlength": 1, "maxlength": 256, "required": True},
    "image": {"type": "b64_icon", "required": True},
    "roles": {"type": "list", "schema": {"coerce": int}},
}

PATCH_EMOJI = {
    "name": {"type": "string", "minlength": 1, "maxlength": 256, "required": True},
    "roles": {"type": "list", "schema": {"coerce": int}},
}


SEARCH_CHANNEL = {
    "content": {"type": "string", "minlength": 1, "required": True},
    "include_nsfw": {"coerce": bool, "default": False},
    "offset": {"coerce": int, "default": 0},
}


GET_MENTIONS = {
    "limit": {"coerce": int, "default": 25},
    "roles": {"coerce": bool, "default": True},
    "everyone": {"coerce": bool, "default": True},
    "guild_id": {"coerce": int, "required": False},
}


VANITY_URL_PATCH = {
    # TODO: put proper values in maybe an invite data type
    "code": {"type": "string", "minlength": 2, "maxlength": 32}
}

WEBHOOK_CREATE = {
    "name": {"type": "string", "minlength": 2, "maxlength": 32, "required": True},
    "avatar": {"type": "b64_icon", "required": False, "nullable": False},
}

WEBHOOK_UPDATE = {
    "name": {"type": "string", "minlength": 2, "maxlength": 32, "required": False},
    # TODO: check if its b64_icon or string since the client
    # could pass an icon hash instead.
    "avatar": {"type": "b64_icon", "required": False, "nullable": False},
    "channel_id": {"coerce": int, "required": False, "nullable": False},
}

WEBHOOK_MESSAGE_CREATE = {
    "content": {"type": "string", "minlength": 0, "maxlength": 2000, "required": False},
    "tts": {"type": "boolean", "required": False},
    "username": {"type": "string", "minlength": 2, "maxlength": 32, "required": False},
    "avatar_url": {"coerce": EmbedURL, "required": False},
    "embeds": {
        "type": "list",
        "required": False,
        "schema": {"type": "dict", "schema": EMBED_OBJECT},
    },
}

BULK_DELETE = {
    "messages": {
        "type": "list",
        "required": True,
        "minlength": 2,
        "maxlength": 100,
        "schema": {"coerce": int},
    }
}

BULK_ACK = {
    "read_states": {
        "type": "list",
        "required": True,
        "minlength": 0,
        "maxlength": 100,
        "schema": {
            "channel_id": {"coerce": int},
            "message_id": {"coerce": int},
        },
    }
}
