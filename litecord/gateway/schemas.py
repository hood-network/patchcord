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

from typing import Dict

from logbook import Logger

from litecord.gateway.errors import DecodeError
from litecord.schemas import LitecordValidator

log = Logger(__name__)


def validate(
    reqjson: Dict,
    schema: Dict,
) -> Dict:
    validator = LitecordValidator(schema)

    try:
        valid = validator.validate(reqjson)
    except Exception:
        log.exception("Error while validating")
        raise DecodeError(f"Error while validating: {reqjson}")

    if not valid:
        errs = validator.errors
        log.warning("Error validating doc {!r}: {!r}", reqjson, errs)
        raise DecodeError(f"Error validating message : {errs!r}")

    return validator.document


BASE = {
    "op": {"type": "number", "required": True},
    "s": {"type": "number", "required": False},
}

IDENTIFY_SCHEMA = {
    **BASE,
    **{
        "d": {
            "type": "dict",
            "schema": {
                "token": {"type": "string", "required": True},
                "compress": {"type": "boolean", "required": False},
                "large_threshold": {"type": "number", "required": False},
                "shard": {"type": "list", "required": False},
                "presence": {"type": "dict", "required": False},
                "intents": {"type": "number", "required": False},
                "properties": {
                    "type": "dict",
                    "required": False,
                    "schema": {
                        "browser": {"type": "string", "required": False},
                        "client_build_number": {"type": "number", "required": False},
                        "client_event_source": {
                            "type": "string",
                            "required": False,
                            "nullable": True,
                        },
                        "client_version": {"type": "string", "required": False},
                        "distro": {"type": "string", "required": False},
                        "os": {"type": "string", "required": False},
                        "os_arch": {"type": "string", "required": False},
                        "os_version": {"type": "string", "required": False},
                        "release_channel": {"type": "string", "required": False},
                        "system_locale": {"type": "string", "required": False},
                        "window_manager": {"type": "string", "required": False},
                        "$browser": {"type": "string", "required": False},
                        "$os": {"type": "string", "required": False},
                        "$device": {"type": "string", "required": False},
                        "device": {"type": "string", "required": False},
                        "referrer": {"type": "string", "required": False},
                        "referrer_current": {"type": "string", "required": False},
                        "referring_domain": {"type": "string", "required": False},
                        "referring_domain_current": {
                            "type": "string",
                            "required": False,
                        },
                        "browser_user_agent": {"type": "string", "required": False},
                        "browser_version": {"type": "string", "required": False},
                    },
                },
                "capabilities": {"type": "number", "required": False},
                "synced_guilds": {
                    "type": "list",
                    "required": False,
                    "schema": {"type": "snowflake"},
                },
                "client_state": {
                    "type": "dict",
                    "required": False,
                    "schema": {
                        # guild_hashes is a Dict with keys being guild ids and
                        # values being a list of 3 strings. this can not be
                        # validated by cerberus
                        "highest_last_message_id": {
                            "anyof_type": ["string", "number"],
                            "required": False,
                        },
                        "read_state_version": {"type": "number", "required": False},
                        "user_guild_settings_version": {
                            "type": "number",
                            "required": False,
                        },
                    },
                },
                "guild_subscriptions": {"type": "boolean", "required": False},
            },
        }
    },
}

RESUME_SCHEMA = {
    **BASE,
    **{
        "d": {
            "type": "dict",
            "schema": {
                "token": {"type": "string", "required": True},
                "session_id": {"type": "string", "required": True},
                "seq": {"type": "number", "required": True, "nullable": True},
            },
        }
    },
}

REQ_GUILD_SCHEMA = {
    **BASE,
    **{
        "d": {
            "type": "dict",
            "schema": {
                "user_ids": {
                    "type": "list",
                    "required": False,
                    "schema": {"type": "string"},
                },
                "query": {"type": "string", "required": False},
                "limit": {"type": "number", "required": False},
                "presences": {"type": "boolean", "required": False},
            },
        }
    },
}

GUILD_SYNC_SCHEMA = {
    **BASE,
    **{
        "d": {
            "type": "list",
            "schema": {"type": "snowflake"},
        }
    },
}


GW_ACTIVITY = {
    "name": {"type": "string", "required": True},
    "type": {"type": "activity_type", "required": True},
    "url": {"type": "string", "required": False, "nullable": True},
    "timestamps": {
        "type": "dict",
        "required": False,
        "schema": {
            "start": {"type": "number", "required": False},
            "end": {"type": "number", "required": False},
        },
    },
    "application_id": {"type": "snowflake", "required": False, "nullable": False},
    "details": {"type": "string", "required": False, "nullable": True},
    "state": {"type": "string", "required": False, "nullable": True},
    "party": {
        "type": "dict",
        "required": False,
        "schema": {
            "id": {"type": "snowflake", "required": False},
            "size": {"type": "list", "required": False},
        },
    },
    "assets": {
        "type": "dict",
        "required": False,
        "schema": {
            "large_image": {"type": "snowflake", "required": False},
            "large_text": {"type": "string", "required": False},
            "small_image": {"type": "snowflake", "required": False},
            "small_text": {"type": "string", "required": False},
        },
    },
    "secrets": {
        "type": "dict",
        "required": False,
        "schema": {
            "join": {"type": "string", "required": False},
            "spectate": {"type": "string", "required": False},
            "match": {"type": "string", "required": False},
        },
    },
    "instance": {"type": "boolean", "required": False},
    "flags": {"type": "number", "required": False},
    "emoji": {
        "type": "dict",
        "required": False,
        "nullable": True,
        "schema": {
            "animated": {"type": "boolean", "required": False, "default": False},
            "id": {"coerce": int, "nullable": True, "default": None},
            "name": {"type": "string", "required": True},
        },
    },
}

GW_STATUS_UPDATE = {
    "status": {"type": "status_external", "required": False, "default": "online"},
    "activities": {
        "type": "list",
        "required": False,
        "schema": {"type": "dict", "schema": GW_ACTIVITY},
    },
    "afk": {"type": "boolean", "required": False},
    "since": {"type": "number", "required": False, "nullable": True},
    "game": {
        "type": "dict",
        "required": False,
        "nullable": True,
        "schema": GW_ACTIVITY,
    },
}
