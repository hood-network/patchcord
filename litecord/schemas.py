import re

from cerberus import Validator

from .errors import BadRequest

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


def validate(reqjson, schema):
    validator = LitecordValidator(schema)
    if not validator.validate(reqjson):
        errs = validator.errors

        raise BadRequest('bad payload', errs)

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
    'nonce': {'type': 'number', 'required': False},
    'tts': {'type': 'boolean', 'required': False},

    # TODO: file, embed, payload_json
}
