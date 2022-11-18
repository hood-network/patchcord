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

from datetime import datetime
from typing import Union, Dict, List, Optional, TYPE_CHECKING

from cerberus import Validator
from cerberus.errors import BasicErrorHandler
from logbook import Logger

from .errors import BadRequest, FormError
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
    NSFWLevel,
)

from litecord.embed.schemas import EMBED_OBJECT, EmbedURL

if TYPE_CHECKING:
    from litecord.typing_hax import app
else:
    from quart import current_app as app

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

    def __init__(self, *args, **kwargs):
        kwargs["allow_unknown"] = True
        kwargs["error_handler"] = LitecordErrorHandler
        super().__init__(*args, **kwargs)

    def _validate_type_username(self, value: str) -> bool:
        """Validate against the username regex."""
        return bool(USERNAME_REGEX.match(value))

    def _validate_type_password(self, value: str) -> bool:
        """Validate a password. Max 72 chars."""
        return 6 <= len(value) <= 72

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

    def _validate_type_snowflake(self, value: Union[int, str]) -> bool:
        try:
            int(value)
            return True
        except (TypeError, ValueError):
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

    def _validate_type_nsfw(self, value: str) -> bool:
        try:
            val = int(value)
        except (TypeError, ValueError):
            return False

        return val in NSFWLevel.values()

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

    def _validate_type_nickname(self, value: str) -> bool:
        return isinstance(value, str) and (len(value) < 32)

    def _validate_type_rgb_int_color(self, value: int) -> bool:
        return isinstance(value, int) and value > 0 and value < 0xFFFFFF

    def _validate_type_rgb_str_color(self, value: str) -> bool:
        try:
            int(value.lstrip("#"), base=16)
        except (TypeError, ValueError):
            return False
        else:
            return True

    def _validate_type_recipients(
        self, value: Union[List[Union[int, str]], Union[int, str]]
    ):
        return (
            all(self._validate_type_snowflake(v) for v in value)
            if isinstance(value, list)
            else self._validate_type_snowflake(value)
        )

    def _validate_type_date_of_birth(self, value: str) -> bool:
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return False
        else:
            return True

    def _validate_type_embed_type(self, value: str) -> bool:
        return value in {"rich", "image", "video", "gifv", "article", "link"}

    def _validate_type_author_type(self, value: str) -> bool:
        return value in {"user", "-user", "bot", "-bot", "webhook", "-webhook"}

    def _validate_type_has(self, value: str) -> bool:
        return value in {
            "video",
            "-link",
            "file",
            "sticker",
            "-embed",
            "-file",
            "-video",
            "-sound",
            "link",
            "-image",
            "-sticker",
            "embed",
            "sound",
            "image",
        }


class LitecordErrorHandler(BasicErrorHandler):
    messages = {
        0x00: {"code": "CUSTOM", "message": "{0}"},
        0x02: {"code": "BASE_TYPE_REQUIRED", "message": "This field is required."},
        0x06: {"code": "BASE_TYPE_REQUIRED", "message": "This field is required."},
        0x22: {"code": "BASE_TYPE_REQUIRED", "message": "This field is required."},
        0x23: {"code": "BASE_TYPE_REQUIRED", "message": "This field is required."},
        0x24: {
            "code": "{constraint}_TYPE_COERCE",
            "message": 'Value "{value}" is not {constraint}.',
        },
        0x25: {
            "code": "DICT_TYPE_CONVERT",
            "message": "Only dictionaries may be used in a DictType.",
        },
        0x27: {
            "code": "BASE_TYPE_BAD_LENGTH",
            "message": "Must be between {0} and {1} in length.",
        },
        0x27: {
            "code": "BASE_TYPE_MIN_LENGTH",
            "message": "Must be {constraint} or more in length.",
        },
        0x28: {
            "code": "BASE_TYPE_MAX_LENGTH",
            "message": "Must be {constraint} or fewer in length.",
        },
        0x41: {"code": "REGEX_VALIDATE", "message": 'Value cannot be "{value}".'},
        0x42: {
            "code": "NUMBER_TYPE_MIN",
            "message": "Value should be greater than or equal to {constraint}.",
        },
        0x43: {
            "code": "NUMBER_TYPE_MAX",
            "message": "Value should be less than or equal to {constraint}.",
        },
        0x44: {
            "code": "BASE_TYPE_CHOICES",
            "message": "Value must be one of {constraint}.",
        },
        0x45: {
            "code": "BASE_TYPE_CHOICES",
            "message": "Values must be one of {constraint}.",
        },
        0x46: {
            "code": "BASE_TYPE_CHOICES",
            "message": "Value cannot be one of {constraint}.",
        },
        0x47: {
            "code": "BASE_TYPE_CHOICES",
            "message": "Values cannot be one of {constraint}.",
        },
        0x47: {
            "code": "BASE_TYPE_CHOICES",
            "message": "Values must contain {constraint}.",
        },
        0x61: {
            "code": "{constraint}_TYPE_COERCE",
            "message": 'Value "{value}" is not {constraint}.',
        },
    }

    def _format_message(self, field, error):
        info = self.messages.get(error.code, self.messages[0x00])
        return {
            "code": info["code"].format(constraint=error.constraint).upper(),
            "message": info["message"].format(
                *error.info, constraint=error.constraint, field=field, value=error.value
            ),
        }


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
        raise BadRequest(50109)

    try:
        valid = validator.validate(reqjson)
    except Exception:
        log.exception("Error while validating")
        raise Exception(f"Error while validating: {reqjson}")

    if not valid:
        errors = validator.errors
        log.warning("Error validating doc {!r}: {!r}", reqjson, errors)
        raise FormError(**errors)

    return validator.document


REGISTER = {
    "username": {"type": "username", "required": True},
    "email": {"type": "email", "required": False},
    "password": {"type": "password", "required": False},
    # invite stands for a guild invite, not an instance invite (that's on
    # the register_with_invite handler).
    "invite": {"coerce": str, "required": False, "nullable": True},
    # following fields only sent by official client, unused by us
    "fingerprint": {"coerce": str, "required": False, "nullable": True},
    "captcha_key": {"coerce": str, "required": False, "nullable": True},
    "gift_code_sku_id": {"coerce": str, "required": False, "nullable": True},
    "consent": {"type": "boolean", "required": False},
    "date_of_birth": {"type": "date_of_birth", "required": False, "nullable": True},
}

LOGIN = {
    "login": {"coerce": str, "required": True},
    "password": {"coerce": str, "required": True},
}

LOGIN_v6 = {
    "email": {"coerce": str, "required": True},
    "password": {"coerce": str, "required": True},
}

# only used by us, not discord, hence 'invcode' (to separate from discord)
REGISTER_WITH_INVITE = {**REGISTER, **{"invcode": {"coerce": str, "required": True}}}


OVERRIDE_SPECIFIC = {
    "type": "dict",
    "required": False,
    "schema": {
        "id": {"coerce": str, "required": True},
        "type": {"coerce": str, "required": True, "allowed": ("id", "branch")},
    },
}

OVERRIDE_STAFF = {
    "overrides": {
        "type": "dict",
        "required": False,
        "schema": {
            "discord_web": OVERRIDE_SPECIFIC,
            "discord_ios": OVERRIDE_SPECIFIC,
            "discord_android": OVERRIDE_SPECIFIC,
            "discord_marketing": OVERRIDE_SPECIFIC,
        },
    },
}

OVERRIDE_LINK = {
    "overrides": {
        **OVERRIDE_STAFF["overrides"],
        "required": True,
        "minlength": 1,
    },
    "meta": {
        "type": "dict",
        "required": True,
        "schema": {
            "allow_logged_out": {
                "type": "boolean",
                "required": False,
                "default": False,
            },
            "release_channel": {"coerce": str, "required": False, "nullable": True},
            "user_ids": {
                "type": "list",
                "required": False,
                "nullable": True,
                "schema": {"coerce": int},
            },
            "ttl_seconds": {
                "type": "number",
                "required": False,
                "nullable": True,
                "default": 3600,
            },
        },
    },
}


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
        "coerce": str,
        "required": False,
        "nullable": True,
    },
    "avatar_decoration": {
        # can be both b64_icon or string (just the hash)
        "coerce": str,
        "required": False,
        "nullable": True,
    },
    "banner": {
        # can be both b64_icon or string (just the hash)
        "coerce": str,
        "required": False,
        "nullable": True,
    },
    "bio": {
        "coerce": str,
        "required": False,
        "nullable": True,
        "maxlength": 190,
    },
    "pronouns": {
        "coerce": str,
        "required": False,
        "nullable": True,
        "maxlength": 40,
    },
    "banner_color": {
        "type": "rgb_str_color",
        "required": False,
        "nullable": True,
    },
    "accent_color": {
        "type": "rgb_int_color",
        "required": False,
        "nullable": True,
    },
    "theme_colors": {
        "type": "list",
        "required": False,
        "nullable": True,
        "schema": {"type": "rgb_int_color", "nullable": False},
        "minlength": 2,
        "maxlength": 2,
    },
    "flags": {
        "coerce": int,
        "required": False,
    },
    "public_flags": {
        "coerce": int,
        "required": False,
    },
    "date_of_birth": {
        "type": "date_of_birth",
        "required": False,
    },
}

PARTIAL_ROLE_GUILD_CREATE = {
    "type": "dict",
    "schema": {
        "name": {"type": "role_name", "required": True},
        "color": {"type": "number", "default": 0},
        "hoist": {"type": "boolean", "default": False},
        # NOTE: no position on partial role (on guild create)
        "permissions": {"coerce": Permissions, "required": False},
        "mentionable": {"type": "boolean", "default": False},
    },
}

PARTIAL_CHANNEL_GUILD_CREATE = {
    "type": "dict",
    "schema": {
        "name": {"type": "channel_name", "required": True},
        "type": {"type": "channel_type", "required": True},
        "id": {"coerce": int, "nullable": True},
        "parent_id": {"coerce": int},
    },
}

GUILD_CREATE = {
    "name": {"type": "guild_name"},
    "icon": {"type": "b64_icon", "required": False, "nullable": True},
    "verification_level": {"type": "verification_level", "default": 0},
    "default_message_notifications": {"type": "msg_notifications", "default": 0},
    "explicit_content_filter": {"type": "explicit", "default": 0},
    "roles": {"type": "list", "default": [], "schema": PARTIAL_ROLE_GUILD_CREATE},
    "channels": {"type": "list", "default": [], "schema": PARTIAL_CHANNEL_GUILD_CREATE},
    "system_channel_id": {"coerce": int, "required": False, "nullable": True},
    "afk_channel_id": {"coerce": int, "required": False, "nullable": True},
    "afk_timeout": {"coerce": int, "required": False, "nullable": True},
    "guild_template_code": {
        "coerce": str,
        "required": False,
    },
}


GUILD_UPDATE = {
    "name": {"type": "guild_name", "required": False},
    "region": {"type": "voice_region", "required": False, "nullable": True},
    # all three can have hashes
    "icon": {"coerce": str, "required": False, "nullable": True},
    "banner": {"coerce": str, "required": False, "nullable": True},
    "splash": {"coerce": str, "required": False, "nullable": True},
    "description": {
        "coerce": str,
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
    "features": {"type": "list", "required": False, "schema": {"coerce": str}},
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
    "preferred_locale": {"coerce": str, "required": False, "nullable": True},
    "discovery_splash": {"coerce": str, "required": False, "nullable": True},
    "premium_progress_bar_enabled": {"type": "boolean", "required": False},
    "nsfw_level": {"type": "nsfw", "required": False},
}


CHAN_OVERWRITE = {
    "id": {"coerce": int},
    "type": {"type": "snowflake", "allowed": ["role", "member", "0", "1", 0, 1]},
    "allow": {"coerce": Permissions, "default": 0},
    "deny": {"coerce": Permissions, "default": 0},
}


CHAN_CREATE = {
    "name": {"coerce": str, "minlength": 1, "maxlength": 100, "required": True},
    "banner": {"coerce": str, "required": False, "nullable": True},
    "type": {
        "coerce": int,
        "default": ChannelType.GUILD_TEXT.value,
        "allowed": (
            ChannelType.GUILD_TEXT.value,
            ChannelType.GUILD_VOICE.value,
            ChannelType.GUILD_CATEGORY.value,
            ChannelType.GUILD_NEWS.value,
        ),
    },
    "position": {"coerce": int, "required": False},
    "topic": {"coerce": str, "minlength": 0, "maxlength": 1024, "required": False},
    "nsfw": {"type": "boolean", "required": False},
    "rate_limit_per_user": {"coerce": int, "min": 0, "max": 120, "required": False},
    "default_auto_archive_duration": {
        "coerce": int,
        "required": False,
        "nullable": True,
    },
    "rtc_region": {"coerce": str, "required": False, "nullable": True},
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
    **{"name": {"coerce": str, "minlength": 1, "maxlength": 100, "required": False}},
}


ROLE_CREATE = {
    "name": {"coerce": str, "default": "new role"},
    "permissions": {"coerce": Permissions, "nullable": True},
    "color": {"coerce": Color, "default": 0},
    "hoist": {"type": "boolean", "default": False},
    "mentionable": {"type": "boolean", "default": False},
}

ROLE_UPDATE = {
    "name": {"coerce": str, "required": False},
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


CHANNEL_UPDATE_POSITION = {
    "channels": {
        "type": "list",
        "schema": {
            "type": "dict",
            "schema": {
                "id": {"coerce": int},
                "position": {"coerce": int},
                "parent_id": {"coerce": int, "required": False, "nullable": True},
                "lock_permissions": {"type": "boolean", "required": False},
            },
        },
    }
}


MEMBER_UPDATE = {
    "avatar": {"coerce": str, "required": False, "nullable": True},
    "banner": {"coerce": str, "required": False, "nullable": True},
    "bio": {"coerce": str, "required": False, "nullable": True, "maxlength": 190},
    "pronouns": {"coerce": str, "required": False, "nullable": True, "maxlength": 40},
    "nick": {"type": "nickname", "required": False, "nullable": True},
    "roles": {
        "type": "list",
        "required": False,
        "schema": {"coerce": int},
        "nullable": True,
    },
    "mute": {"type": "boolean", "required": False},
    "deaf": {"type": "boolean", "required": False},
    "channel_id": {"type": "snowflake", "required": False, "nullable": True},
}


SELF_MEMBER_UPDATE = {
    "avatar": {"coerce": str, "required": False, "nullable": True},
    "banner": {"coerce": str, "required": False, "nullable": True},
    "bio": {"coerce": str, "required": False, "nullable": True, "maxlength": 190},
    "pronouns": {"coerce": str, "required": False, "nullable": True, "maxlength": 40},
    "nick": {"type": "nickname", "required": False, "nullable": True},
}


# NOTE: things such as payload_json are parsed at the handler
# for creating a message.


CHANNEL_GREET = {
    "sticker_ids": {
        "type": "list",
        "required": True,
        "schema": {"coerce": int},
        "maxlength": 3,
    },
    "message_reference": {
        "type": "dict",
        "required": False,
        "nullable": True,
        "schema": {
            "guild_id": {"coerce": str, "required": False},
            "channel_id": {"coerce": str, "required": True},
            "message_id": {"coerce": str, "required": True},
        },
    },
}


MESSAGE_UPDATE = {
    "type": {"type": "snowflake", "required": False},
    "attachments": {"type": "list", "required": False, "schema": {"type": "dict"}},
    "content": {"coerce": str, "minlength": 0, "maxlength": 4000, "required": False},
    "embed": {
        "type": "dict",
        "schema": EMBED_OBJECT,
        "required": False,
        "nullable": True,
    },
    "embeds": {
        "type": "list",
        "required": False,
        "schema": {"type": "dict", "schema": EMBED_OBJECT},
        "nullable": True,
        "maxlength": 10,
    },
    "allowed_mentions": {
        "type": "dict",
        "required": False,
        "nullable": True,
        "schema": {
            "parse": {
                "type": "list",
                "required": False,
                "allowed": ("everyone", "roles", "users"),
            },
            "replied_user": {"type": "boolean", "default": False},
            "roles": {"type": "list", "required": False, "schema": {"coerce": int}},
            "users": {"type": "list", "required": False, "schema": {"coerce": int}},
        },
    },
    "flags": {"coerce": int, "required": False},
}


MESSAGE_CREATE = {
    **MESSAGE_UPDATE,
    **CHANNEL_GREET,
    "sticker_ids": {
        "type": "list",
        "required": False,
        "schema": {"coerce": int},
        "maxlength": 3,
    },
    "channel_id": {"type": "snowflake", "required": False},
    "nonce": {"coerce": str, "required": False, "nullable": True},
    "tts": {"type": "boolean", "default": False},
}


INVITE = {
    # max_age in seconds
    # 0 for infinite
    "max_age": {
        "coerce": int,
        "min": 0,
        "max": 666666,  # TODO find correct max value
        # a day
        "default": 86400,
    },
    # max invite uses
    "max_uses": {
        "coerce": int,
        "min": 0,
        "max": 1000,
        "default": 0,
    },
    "temporary": {"type": "boolean", "required": False, "default": False},
    "unique": {"type": "boolean", "required": False, "default": True},
    "validate": {
        "coerce": str,
        "required": False,
        "nullable": True,
    },
    "target_type": {"coerce": str, "required": False, "nullable": True},
    "target_user_id": {"type": "snowflake", "required": False, "nullable": True},
    "target_user_type": {"type": "number", "required": False, "nullable": True},
}


def removeunknown(value: str):
    return value if value.lower() != "unknown" else "online"


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
    "status": {"type": "status_external", "required": False, "coerce": removeunknown},
    "theme": {"coerce": str, "allowed": ("light", "dark"), "required": False},
    "custom_status": {
        "type": "dict",
        "required": False,
        "nullable": True,
        "schema": {
            "emoji_id": {"coerce": int, "nullable": True},
            "emoji_name": {"coerce": str, "nullable": True},
            # discord's timestamps dont seem to work well with
            # datetime.fromisoformat, so for now, we trust the client
            "expires_at": {"coerce": str, "nullable": True},
            "text": {"coerce": str, "nullable": True},
        },
    },
}

RELATIONSHIP = {
    "type": {
        "coerce": int,
        "allowed": (RelationshipType.FRIEND.value, RelationshipType.BLOCK.value),
        "default": RelationshipType.FRIEND.value,
    }
}

RELATIONSHIP_UPDATE = {
    "nickname": {"coerce": str, "required": False, "nullable": True, "maxlength": 32},
}

CREATE_DM = {"recipient_id": {"type": "recipients", "required": True}}

CREATE_DM_V9 = {"recipients": {"type": "recipients", "required": True}}

GROUP_DM_UPDATE = {
    "name": {"type": "guild_name", "required": False},
    "icon": {"type": "b64_icon", "required": False, "nullable": True},
    "owner": {"type": "snowflake", "coerce": int, "required": False, "nullable": True},
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
    "compute_prune_count": {"coerce": str, "default": "true"},
}

NEW_EMOJI = {
    "name": {"coerce": str, "minlength": 1, "maxlength": 256, "required": True},
    "image": {"type": "b64_icon", "required": True},
    "roles": {"type": "list", "schema": {"coerce": int}},
}

PATCH_EMOJI = {
    "name": {"coerce": str, "minlength": 1, "maxlength": 256, "required": True},
    "roles": {"type": "list", "schema": {"coerce": int}},
}


def maybebool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if value.lower() in {"true", "1"}:
        return True
    if value.lower() in {"false", "0"}:
        return False
    return None


SEARCH_CHANNEL = {
    "content": {
        "coerce": str,
        "minlength": 1,
        "maxlength": 4096,
        "required": False,
        "nullable": True,
    },
    "include_nsfw": {"coerce": maybebool, "default": True},
    "offset": {"coerce": int, "default": 0},
    "min_id": {"coerce": int, "required": False},
    "max_id": {"coerce": int, "required": False},
    "channel_id": {"type": "list", "schema": {"coerce": int}, "required": False},
    "author_id": {"type": "list", "schema": {"coerce": int}, "required": False},
    "author_type": {
        "type": "list",
        "schema": {"type": "author_type"},
        "required": False,
    },
    "has": {"type": "list", "schema": {"type": "has"}, "required": False},
    "mentions": {"type": "list", "schema": {"coerce": int}, "required": False},
    "embed_type": {"type": "list", "schema": {"coerce": str}, "required": False},
    "embed_provider": {"type": "list", "schema": {"coerce": str}, "required": False},
    "link_hostname": {"type": "list", "schema": {"coerce": str}, "required": False},
    "attachment_filename": {
        "type": "list",
        "schema": {"coerce": str},
        "required": False,
    },
    "attachment_extension": {
        "type": "list",
        "schema": {"coerce": str},
        "required": False,
    },
    "limit": {"coerce": int, "default": 25, "min": 1, "max": 25},
    "sort_by": {"coerce": str, "required": False},
    "sort_order": {"coerce": str, "allowed": ("asc", "desc"), "default": "desc"},
    "mention_everyone": {"coerce": maybebool, "default": None, "nullable": True},
    "pinned": {"coerce": maybebool, "default": None, "nullable": True},
}


GET_MENTIONS = {
    "limit": {"coerce": int, "default": 25},
    "roles": {"coerce": bool, "default": True},
    "everyone": {"coerce": bool, "default": True},
    "guild_id": {"coerce": int, "required": False},
}


VANITY_URL_PATCH = {
    # TODO: put proper values in maybe an invite data type
    "code": {"coerce": str, "required": True, "minlength": 2, "maxlength": 32}
}

MFA_TOGGLE = {
    "level": {"coerce": int, "required": True, "allowed": (0, 1)},
}

WEBHOOK_CREATE = {
    "name": {"coerce": str, "minlength": 2, "maxlength": 32, "required": True},
    "avatar": {"type": "b64_icon", "required": False, "nullable": True},
}

WEBHOOK_UPDATE = {
    **WEBHOOK_CREATE,
    "name": {"coerce": str, "minlength": 2, "maxlength": 32, "required": False},
    "channel_id": {"coerce": int, "required": False, "nullable": False},
}


WEBHOOK_MESSAGE_UPDATE = {
    "content": {"coerce": str, "minlength": 1, "maxlength": 2000, "required": False},
    "embeds": {
        "type": "list",
        "required": False,
        "schema": {"type": "dict", "schema": EMBED_OBJECT},
        "nullable": True,
        "maxlength": 10,
    },
    "embed": {"type": "dict", "schema": EMBED_OBJECT, "required": False},
    "allowed_mentions": {
        "type": "dict",
        "required": False,
        "nullable": True,
        "schema": {
            "parse": {
                "type": "list",
                "required": False,
                "allowed": ("everyone", "roles", "users"),
            },
            "replied_user": {"type": "boolean", "required": False},
            "roles": {"type": "list", "required": False, "schema": {"coerce": int}},
            "users": {"type": "list", "required": False, "schema": {"coerce": int}},
        },
    },
}


WEBHOOK_MESSAGE_CREATE = {
    **WEBHOOK_MESSAGE_UPDATE,
    "tts": {"type": "boolean", "default": False},
    "username": {"coerce": str, "minlength": 2, "maxlength": 80, "required": False},
    "avatar_url": {"coerce": EmbedURL, "required": False},
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

FOLLOW_CHANNEL = {
    "webhook_channel_id": {"coerce": int, "required": True},
}
