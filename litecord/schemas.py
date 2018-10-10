import re

from cerberus import Validator
from logbook import Logger

from .errors import BadRequest
from .enums import ActivityType, StatusType, ExplicitFilter, RelationshipType


log = Logger(__name__)

USERNAME_REGEX = re.compile(r'^[a-zA-Z0-9_]{2,19}$', re.A)
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$',
                         re.A)


# collection of regexes
USER_MENTION = re.compile(r'<@!?(\d+)>', re.A | re.M)
CHAN_MENTION = re.compile(r'<#(\d+)>', re.A | re.M)
ROLE_MENTION = re.compile(r'<@&(\d+)>', re.A | re.M)
EMOJO_MENTION = re.compile(r'<:(\.+):(\d+)>', re.A | re.M)
ANIMOJI_MENTION = re.compile(r'<a:(\.+):(\d+)>', re.A | re.M)


class LitecordValidator(Validator):
    def _validate_type_username(self, value: str) -> bool:
        """Validate against the username regex."""
        return bool(USERNAME_REGEX.match(value))

    def _validate_type_snowflake(self, value: str) -> bool:
        try:
            int(value)
            return True
        except ValueError:
            return False

    def _validate_type_voice_region(self, value: str) -> bool:
        # TODO: complete this list
        return value in ('brazil', 'us-east', 'us-west', 'us-south', 'russia')

    def _validate_type_activity_type(self, value: int) -> bool:
        return value in ActivityType.values()

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


def validate(reqjson, schema, raise_err: bool = True):
    validator = LitecordValidator(schema)

    if not validator.validate(reqjson):
        errs = validator.errors
        log.warning('Error validating doc {!r}: {!r}', reqjson, errs)

        if raise_err:
            raise BadRequest('bad payload', errs)

        return None

    return validator.document


GUILD_UPDATE = {
    'name': {
        'type': 'string',
        'minlength': 2,
        'maxlength': 100,
        'required': False
    },
    'region': {'type': 'voice_region', 'required': False},
    'icon': {'type': 'icon', 'required': False},

    'verification_level': {'type': 'verification_level', 'required': False},
    'default_message_notifications': {
        'type': 'msg_notifications',
        'required': False,
    },
    'explicit_content_filter': {'type': 'explicit', 'required': False},

    'afk_channel_id': {'type': 'snowflake', 'required': False},
    'afk_timeout': {'type': 'number', 'required': False},

    'owner_id': {'type': 'snowflake', 'required': False},

    'system_channel_id': {'type': 'snowflake', 'required': False},
}


MEMBER_UPDATE = {
    'nick': {
        'type': 'nickname',
        'minlength': 1, 'maxlength': 100,
        'required': False,
    },
    'roles': {'type': 'list', 'required': False},
    'mute': {'type': 'bool', 'required': False},
    'deaf': {'type': 'bool', 'required': False},
    'channel_id': {'type': 'snowflake', 'required': False},
}


MESSAGE_CREATE = {
    'content': {'type': 'string', 'minlength': 1, 'maxlength': 2000},
    'nonce': {'type': 'snowflake', 'required': False},
    'tts': {'type': 'boolean', 'required': False},

    # TODO: file, embed, payload_json
}


GW_ACTIVITY = {
    'name': {'type': 'string', 'required': True},
    'type': {'type': 'activity_type', 'required': True},

    'url': {'type': 'string', 'required': False, 'nullable': True},

    'timestamps': {
        'type': 'dict',
        'required': False,
        'schema': {
            'start': {'type': 'number', 'required': True},
            'end': {'type': 'number', 'required': True},
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
    'type': 'list',
    'required': True,
    'schema': {'type': 'snowflake'}
}

SPECIFIC_FRIEND = {
    'username': {'type': 'username'},
    'discriminator': {'type': 'number'}
}
