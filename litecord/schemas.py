import re
from typing import Union, Dict, List

from cerberus import Validator
from logbook import Logger

from .errors import BadRequest
from .permissions import Permissions
from .types import Color
from .enums import (
    ActivityType, StatusType, ExplicitFilter, RelationshipType,
    MessageNotifications, ChannelType, VerificationLevel
)


log = Logger(__name__)

USERNAME_REGEX = re.compile(r'^[a-zA-Z0-9_]{2,19}$', re.A)
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$',
                         re.A)
DATA_REGEX = re.compile(r'data\:image/(png|jpeg|gif);base64,(.+)', re.A)


# collection of regexes
USER_MENTION = re.compile(r'<@!?(\d+)>', re.A | re.M)
CHAN_MENTION = re.compile(r'<#(\d+)>', re.A | re.M)
ROLE_MENTION = re.compile(r'<@&(\d+)>', re.A | re.M)
EMOJO_MENTION = re.compile(r'<:(\.+):(\d+)>', re.A | re.M)
ANIMOJI_MENTION = re.compile(r'<a:(\.+):(\d+)>', re.A | re.M)


def _in_enum(enum, value: int):
    try:
        enum(value)
        return True
    except ValueError:
        return False


class LitecordValidator(Validator):
    def _validate_type_username(self, value: str) -> bool:
        """Validate against the username regex."""
        return bool(USERNAME_REGEX.match(value))

    def _validate_type_email(self, value: str) -> bool:
        """Validate against the email regex."""
        return bool(EMAIL_REGEX.match(value))

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
        # TODO: complete this list
        return value.lower() in ('brazil', 'us-east', 'us-west',
                                 'us-south', 'russia')

    def _validate_type_verification_level(self, value: int) -> bool:
        return _in_enum(VerificationLevel, value)

    def _validate_type_activity_type(self, value: int) -> bool:
        return value in ActivityType.values()

    def _validate_type_channel_type(self, value: int) -> bool:
        return value in ChannelType.values()

    def _validate_type_status_external(self, value: str) -> bool:
        statuses = StatusType.values()

        # clients should send INVISIBLE instead of OFFLINE
        statuses.remove(StatusType.OFFLINE.value)

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

        return val in (RelationshipType.FRIEND.value,
                       RelationshipType.BLOCK.value)

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


def validate(reqjson: Union[Dict, List], schema: Dict,
             raise_err: bool = True) -> Union[Dict, List]:
    """Validate a given document (user-input) and give
    the correct document as a result.
    """
    validator = LitecordValidator(schema)

    try:
        valid = validator.validate(reqjson)
    except Exception:
        log.exception('Error while validating')
        raise Exception(f'Error while validating: {reqjson}')

    if not valid:
        errs = validator.errors
        log.warning('Error validating doc {!r}: {!r}', reqjson, errs)

        if raise_err:
            raise BadRequest('bad payload', errs)

        return None

    return validator.document


REGISTER = {
    'email': {'type': 'email', 'required': True},
    'username': {'type': 'username', 'required': True},
    'password': {'type': 'string', 'minlength': 5, 'required': True}
}

REGISTER_WITH_INVITE = {**REGISTER, **{
    'invcode': {'type': 'string', 'required': True}
}}


USER_UPDATE = {
    'username': {
        'type': 'username', 'minlength': 2,
        'maxlength': 30, 'required': False},

    'discriminator': {
        'type': 'discriminator',
        'required': False,
        'nullable': True,
    },

    'password': {
        'type': 'string', 'minlength': 0,
        'maxlength': 100, 'required': False,
    },

    'new_password': {
        'type': 'string', 'minlength': 5,
        'maxlength': 100, 'required': False,
        'dependencies': 'password',
        'nullable': True
    },

    'email': {
        'type': 'string', 'minlength': 2,
        'maxlength': 30, 'required': False,
        'dependencies': 'password',
    },

    'avatar': {
        'type': 'b64_icon', 'required': False,
        'nullable': True
    },

}

PARTIAL_ROLE_GUILD_CREATE = {
    'type': 'dict',
    'schema': {
        'name': {'type': 'role_name'},
        'color': {'type': 'number', 'default': 0},
        'hoist': {'type': 'boolean', 'default': False},

        # NOTE: no position on partial role (on guild create)

        'permissions': {'coerce': Permissions, 'required': False},
        'mentionable': {'type': 'boolean', 'default': False},
    }
}

PARTIAL_CHANNEL_GUILD_CREATE = {
    'type': 'dict',
    'schema': {
        'name': {'type': 'channel_name'},
        'type': {'type': 'channel_type'},
    }
}

GUILD_CREATE = {
    'name': {'type': 'guild_name'},
    'region': {'type': 'voice_region'},
    'icon': {'type': 'b64_icon', 'required': False, 'nullable': True},

    'verification_level': {
        'type': 'verification_level', 'default': 0},
    'default_message_notifications': {
        'type': 'msg_notifications', 'default': 0},
    'explicit_content_filter': {
        'type': 'explicit', 'default': 0},

    'roles': {
        'type': 'list', 'required': False,
        'schema': PARTIAL_ROLE_GUILD_CREATE},
    'channels': {
        'type': 'list', 'default': [], 'schema': PARTIAL_CHANNEL_GUILD_CREATE},
}


GUILD_UPDATE = {
    'name': {
        'type': 'guild_name',
        'required': False
    },
    'region': {'type': 'voice_region', 'required': False},
    'icon': {'type': 'b64_icon', 'required': False},
    'splash': {'type': 'b64_icon', 'required': False, 'nullable': True},

    'verification_level': {
        'type': 'verification_level', 'required': False},
    'default_message_notifications': {
        'type': 'msg_notifications', 'required': False},
    'explicit_content_filter': {'type': 'explicit', 'required': False},

    'afk_channel_id': {
        'type': 'snowflake', 'required': False, 'nullable': True},
    'afk_timeout': {'type': 'number', 'required': False},

    'owner_id': {'type': 'snowflake', 'required': False},

    'system_channel_id': {
        'type': 'snowflake', 'required': False, 'nullable': True},
}


CHAN_OVERWRITE = {
    'id': {'coerce': int},
    'type': {'type': 'string', 'allowed': ['role', 'member']},
    'allow': {'coerce': Permissions},
    'deny': {'coerce': Permissions}
}


CHAN_UPDATE = {
    'name': {
        'type': 'string', 'minlength': 2,
        'maxlength': 100, 'required': False},

    'position': {'coerce': int, 'required': False},

    'topic': {
        'type': 'string', 'minlength': 0,
        'maxlength': 1024, 'required': False},

    'nsfw': {'type': 'boolean', 'required': False},
    'rate_limit_per_user': {
        'coerce': int, 'min': 0,
        'max': 120, 'required': False},

    'bitrate': {
        'coerce': int, 'min': 8000,

        # NOTE: 'max' is 96000 for non-vip guilds
        'max': 128000, 'required': False},

    'user_limit': {
        # user_limit being 0 means infinite.
        'coerce': int, 'min': 0,
        'max': 99, 'required': False
    },

    'permission_overwrites': {
        'type': 'list',
        'schema': {'type': 'dict', 'schema': CHAN_OVERWRITE},
        'required': False
    },

    'parent_id': {'coerce': int, 'required': False, 'nullable': True}


}


ROLE_CREATE = {
    'name': {'type': 'string', 'default': 'new role'},
    'permissions': {'coerce': Permissions, 'nullable': True},
    'color': {'coerce': Color, 'default': 0},
    'hoist': {'type': 'boolean', 'default': False},
    'mentionable': {'type': 'boolean', 'default': False},
}

ROLE_UPDATE = {
    'name': {'type': 'string', 'required': False},
    'permissions': {'coerce': Permissions, 'required': False},
    'color': {'coerce': Color, 'required': False},
    'hoist': {'type': 'boolean', 'required': False},
    'mentionable': {'type': 'boolean', 'required': False},
}


ROLE_UPDATE_POSITION = {
    'roles': {
        'type': 'list',
        'schema': {
            'type': 'dict',
            'schema': {
                'id': {'coerce': int},
                'position': {'coerce': int},
            },
        }
    }
}


MEMBER_UPDATE = {
    'nick': {
        'type': 'username',
        'minlength': 1, 'maxlength': 100,
        'required': False,
    },
    'roles': {'type': 'list', 'required': False,
              'schema': {'coerce': int}},
    'mute': {'type': 'boolean', 'required': False},
    'deaf': {'type': 'boolean', 'required': False},
    'channel_id': {'type': 'snowflake', 'required': False},
}


MESSAGE_CREATE = {
    'content': {'type': 'string', 'minlength': 1, 'maxlength': 2000},
    'nonce': {'type': 'snowflake', 'required': False},
    'tts': {'type': 'boolean', 'required': False},

    # TODO: file, embed, payload_json
}


GW_ACTIVITY = {
    'type': 'dict',
    'schema': {
        'name': {'type': 'string', 'required': True},
        'type': {'type': 'activity_type', 'required': True},

        'url': {'type': 'string', 'required': False, 'nullable': True},

        'timestamps': {
            'type': 'dict',
            'required': False,
            'schema': {
                'start': {'type': 'number', 'required': True},
                'end': {'type': 'number', 'required': False},
            },
        },

        'application_id': {'type': 'snowflake', 'required': False,
                           'nullable': False},
        'details': {'type': 'string', 'required': False, 'nullable': True},
        'state': {'type': 'string', 'required': False, 'nullable': True},

        'party': {
            'type': 'dict',
            'required': False,
            'schema': {
                'id': {'type': 'snowflake', 'required': False},
                'size': {'type': 'list', 'required': False},
            }
        },

        'assets': {
            'type': 'dict',
            'required': False,
            'schema': {
                'large_image': {'type': 'snowflake', 'required': False},
                'large_text': {'type': 'string', 'required': False},
                'small_image': {'type': 'snowflake', 'required': False},
                'small_text': {'type': 'string', 'required': False},
            }
        },

        'secrets': {
            'type': 'dict',
            'required': False,
            'schema': {
                'join': {'type': 'string', 'required': False},
                'spectate': {'type': 'string', 'required': False},
                'match': {'type': 'string', 'required': False},
            }
        },

        'instance': {'type': 'boolean', 'required': False},
        'flags': {'type': 'number', 'required': False},
    }
}

GW_STATUS_UPDATE = {
    'status': {'type': 'status_external', 'required': False},
    'activities': {
        'type': 'list', 'required': False, 'schema': GW_ACTIVITY},
    'afk': {'type': 'boolean', 'required': False},

    'since': {'type': 'number', 'required': True, 'nullable': True},
    'game': {
        'type': 'dict',
        'required': False,
        'nullable': True,
        'schema': GW_ACTIVITY,
    },
}

INVITE = {
    # max_age in seconds
    # 0 for infinite
    'max_age': {
        'type': 'number',
        'min': 0,
        'max': 86400,

        # a day
        'default': 86400
    },

    # max invite uses
    'max_uses': {
        'type': 'number',
        'min': 0,

        # idk
        'max': 1000,

        # default infinite
        'default': 0
    },

    'temporary': {'type': 'boolean', 'required': False, 'default': False},
    'unique': {'type': 'boolean', 'required': False, 'default': True},
    'validate': {'type': 'boolean', 'required': False, 'nullable': True}
}

USER_SETTINGS = {
    'afk_timeout': {
        'type': 'number', 'required': False, 'min': 0, 'max': 3000},

    'animate_emoji': {'type': 'boolean', 'required': False},
    'convert_emoticons': {'type': 'boolean', 'required': False},
    'default_guilds_restricted': {'type': 'boolean', 'required': False},
    'detect_platform_accounts': {'type': 'boolean', 'required': False},
    'developer_mode': {'type': 'boolean', 'required': False},
    'disable_games_tab': {'type': 'boolean', 'required': False},
    'enable_tts_command': {'type': 'boolean', 'required': False},

    'explicit_content_filter': {'type': 'explicit', 'required': False},

    'friend_source': {
        'type': 'dict',
        'required': False,
        'schema': {
            'all': {'type': 'boolean', 'required': False},
            'mutual_guilds': {'type': 'boolean', 'required': False},
            'mutual_friends': {'type': 'boolean', 'required': False},
        }
    },
    'guild_positions': {
        'type': 'list',
        'required': False,
        'schema': {'type': 'snowflake'}
    },
    'restricted_guilds': {
        'type': 'list',
        'required': False,
        'schema': {'type': 'snowflake'}
    },

    'gif_auto_play': {'type': 'boolean', 'required': False},
    'inline_attachment_media': {'type': 'boolean', 'required': False},
    'inline_embed_media': {'type': 'boolean', 'required': False},
    'message_display_compact': {'type': 'boolean', 'required': False},
    'render_embeds': {'type': 'boolean', 'required': False},
    'render_reactions': {'type': 'boolean', 'required': False},
    'show_current_game': {'type': 'boolean', 'required': False},

    'timezone_offset': {'type': 'number', 'required': False},

    'status': {'type': 'status_external', 'required': False}
}

RELATIONSHIP = {
    'type': {
        'type': 'rel_type',
        'required': False,
        'default': RelationshipType.FRIEND.value
    }
}

CREATE_DM = {
    'recipient_id': {
        'type': 'snowflake',
        'required': True
    }
}

CREATE_GROUP_DM = {
    'recipients': {
        'type': 'list',
        'required': True,
        'schema': {'type': 'snowflake'}
    },
}

SPECIFIC_FRIEND = {
    'username': {'type': 'username'},
    'discriminator': {'type': 'discriminator'}
}

GUILD_SETTINGS_CHAN_OVERRIDE = {
    'type': 'dict',
    'schema': {
        'muted': {
            'type': 'boolean', 'required': False},
        'message_notifications': {
            'type': 'msg_notifications',
            'required': False,
        }
    }
}

GUILD_SETTINGS = {
    'channel_overrides': {
        'type': 'dict',
        'valueschema': GUILD_SETTINGS_CHAN_OVERRIDE,
        'keyschema': {'type': 'snowflake'},
        'required': False,
    },
    'suppress_everyone': {
        'type': 'boolean', 'required': False},
    'muted': {
        'type': 'boolean', 'required': False},
    'mobile_push': {
        'type': 'boolean', 'required': False},
    'message_notifications': {
        'type': 'msg_notifications',
        'required': False,
    }
}

GUILD_PRUNE = {
    'days': {'type': 'number', 'coerce': int, 'min': 1}
}

NEW_EMOJI = {
    'name': {
        'type': 'string', 'minlength': 1, 'maxlength': 256, 'required': True},
    'image': {'type': 'b64_icon', 'required': True},
    'roles': {'type': 'list', 'schema': {'coerce': int}}
}

PATCH_EMOJI = {
    'name': {
        'type': 'string', 'minlength': 1, 'maxlength': 256, 'required': True},
    'roles': {'type': 'list', 'schema': {'coerce': int}}
}
