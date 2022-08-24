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

ERR_MSG_MAP = {
    10001: "Unknown Account",
    10002: "Unknown Application",
    10003: "Unknown Channel",
    10004: "Unknown Guild",
    10005: "Unknown Integration",
    10006: "Unknown Invite",
    10007: "Unknown Member",
    10008: "Unknown Message",
    10009: "Unknown Overwrite",
    10010: "Unknown Provider",
    10011: "Unknown Role",
    10012: "Unknown Token",
    10013: "Unknown User",
    10014: "Unknown Emoji",
    10015: "Unknown Webhook",
    10061: "Unknown sticker pack",
    20001: "Bots cannot use this endpoint",
    20002: "Only bots can use this endpoint",
    20024: "Under minimum age",
    20017: "The Maze isn't meant for you.",
    30001: "Maximum number of guilds reached ({})",
    30002: "Maximum number of friends reached (1000)",
    30003: "Maximum number of pins reached (50)",
    30005: "Maximum number of guild roles reached (250)",
    30006: "Too many users have this username, please try another.",
    30008: "Maximum number of emojis reached ({})",
    30010: "Maximum number of reactions reached (20)",
    30013: "Maximum number of guild channels reached (500)",
    30016: "Maximum number of invites reached (1000)",
    40001: "Unauthorized",
    40005: "Request entity too large",
    40007: "The user is banned from this guild",
    40008: "Invites are currently paused for this server. Please try again later.",
    40011: "You must transfer ownership of any owned guilds before deleting your account",
    40015: "You must transfer ownership of any owned guilds before disabling your account",
    40033: "This message has already been crossposted.",
    50001: "Missing access",
    50002: "Invalid account type",
    50003: "Cannot execute action on a DM channel",
    50004: "Widget Disabled",
    50005: "Cannot edit a message authored by another user",
    50006: "Cannot send an empty message",
    50007: "Cannot send messages to this user",
    50008: "Cannot send messages in a non-text channel",
    50009: "Channel verification level is too high",
    50010: "OAuth2 application does not have a bot",
    50011: "OAuth2 application limit reached",
    50012: "Invalid OAuth state",
    50013: "Missing permissions",
    50014: "Invalid authentication token",
    50015: "Note is too long",
    50016: (
        "Provided too few or too many messages to delete. Must provide at "
        "least 2 and fewer than 100 messages to delete."
    ),
    50019: "A message can only be pinned to the channel it was sent in",
    50020: "Invite code is either invalid or taken",
    50021: "Cannot execute action on a system message",
    50024: "Cannot execute action on this channel type",
    50025: "Invalid OAuth2 access token",
    50034: "A message provided was too old to bulk delete",
    50035: "Invalid Form Body",
    50036: "An invite was accepted to a guild the application's bot is not in",
    50041: "Invalid API version",
    50055: "Invalid guild",
    50068: "Invalid message type",
    50109: "The request body contains invalid JSON.",
    80001: "Friend request blocked",
    80003: "Cannot send friend request to self",
    80004: "No users with DiscordTag exist",
    80006: "You need to be friends in order to make this change.",
    90001: "Reaction blocked",
    100002: "Invalid payment source",
    100037: "Subscription items are required",
}


class LitecordError(Exception):
    """Base class for litecord errors"""

    status_code = 500
    error_code = 0
    default_message = "Unknown error"

    def __init__(self, error_code: int = 0, *args, **kwargs):
        if error_code:
            self.error_code = error_code
        self.args = args
        self.json = kwargs

    @property
    def message(self) -> str:
        """Get an error's message string."""
        return ERR_MSG_MAP.get(self.error_code, self.default_message).format(*self.args)


class BadRequest(LitecordError):
    status_code = 400
    default_message = "400: Bad Request"


class Unauthorized(LitecordError):
    status_code = 401
    error_code = 0
    default_message = "401: Unauthorized"


class Forbidden(LitecordError):
    status_code = 403
    default_message = "403: Forbidden"


class NotFound(LitecordError):
    status_code = 404
    default_message = "404: Not Found"


class Ratelimited(LitecordError):
    status_code = 429
    error_code = -1
    default_message = "You are being rate limited."


class TooLarge(LitecordError):
    status_code = 413
    error_code = 40005
    default_message = "Request entity too large"


class FormError(LitecordError):
    status_code = 400
    error_code = 50035

    def __init__(self, **kwargs):
        self.json = {"errors": self._wrap_errors(kwargs)}

    def _wrap_errors(self, errors: dict) -> dict:
        res = {}
        for k, v in errors.items():
            if isinstance(v, list):
                res[k] = {"_errors": v}
            else:
                res[k] = self._wrap_errors(v)
        return res


class ManualFormError(LitecordError):
    status_code = 400
    error_code = 50035

    def __init__(self, **kwargs):
        self.json = {"errors": self._wrap_errors(kwargs)}

    def _wrap_errors(self, errors: dict) -> dict:
        res = {}
        for k, v in errors.items():
            if "code" in v and "message" in v:
                res[k] = {"_errors": [v]}
            else:
                res[k] = self._wrap_errors(v)
        return res


class MissingAccess(Forbidden):
    error_code = 50001


class MissingPermissions(Forbidden):
    error_code = 50013


class InternalServerError(LitecordError):
    status_code = 500
    default_message = "500: Internal Server Error"


class WebsocketClose(Exception):
    @property
    def code(self):
        from_class = getattr(self, "close_code", None)

        if from_class:
            return from_class

        return self.args[0]

    @property
    def reason(self):
        from_class = getattr(self, "close_code", None)

        if from_class:
            return self.args[0]

        return self.args[1]
