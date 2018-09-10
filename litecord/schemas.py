import re

from cerberus import Validator

from .errors import BadRequest
from .enums import ActivityType, StatusType

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


def validate(reqjson, schema, raise_err: bool = True):
    validator = LitecordValidator(schema)
    if not validator.validate(reqjson):
        errs = validator.errors

        if raise_err:
            raise BadRequest('bad payload', errs)

        return None

    return reqjson


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
    'explicit_content_filter': {'type': 'explicit_content', 'required': False},

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
    'nonce': {'type': 'string', 'required': False},
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
    'afk': {'type': 'boolean', 'required': False},

    'since': {'type': 'number', 'required': True, 'nullable': True},
    'game': {
        'type': 'dict',
        'required': True,
        'nullable': True,
        'schema': GW_ACTIVITY,
    },
}
