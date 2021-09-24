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
    10001: "Unknown account",
    10002: "Unknown application",
    10003: "Unknown channel",
    10004: "Unknown guild",
    10005: "Unknown integration",
    10006: "Unknown invite",
    10007: "Unknown member",
    10008: "Unknown message",
    10009: "Unknown overwrite",
    10010: "Unknown provider",
    10011: "Unknown role",
    10012: "Unknown token",
    10013: "Unknown user",
    10014: "Unknown Emoji",
    10015: "Unknown Webhook",
    20001: "Bots cannot use this endpoint",
    20002: "Only bots can use this endpoint",
    30001: "Maximum number of guilds reached (100)",
    30002: "Maximum number of friends reached (1000)",
    30003: "Maximum number of pins reached (50)",
    30005: "Maximum number of guild roles reached (250)",
    30010: "Maximum number of reactions reached (20)",
    30013: "Maximum number of guild channels reached (500)",
    30016: "Maximum number of invites reached (1000)",
    40001: "Unauthorized",
    40007: "The user is banned from this guild",
    50001: "Missing access",
    50002: "Invalid account type",
    50003: "Cannot execute action on a DM channel",
    50004: "Widget Disabled",
    50005: "Cannot edit a message authored by another user",
    50006: "Cannot send an empty message",
    50007: "Cannot send messages to this user",
    50008: "Cannot send messages in a voice channel",
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
    50020: "Invite code is either invalid or taken.",
    50021: "Cannot execute action on a system message",
    50025: "Invalid OAuth2 access token",
    50034: "A message provided was too old to bulk delete",
    50035: "Invalid Form Body",
    50036: "An invite was accepted to a guild the application's bot is not in",
    50041: "Invalid API version",
    50055: "Invalid guild",
    90001: "Reaction blocked",
}


class LitecordError(Exception):
    """Base class for litecord errors"""

    status_code = 500

    def _get_err_msg(self, err_code: int) -> str:
        if err_code is not None:
            return ERR_MSG_MAP.get(err_code) or self.args[0]

        return repr(self)

    @property
    def message(self) -> str:
        """Get an error's message string."""
        try:
            message = self.args[0]

            if isinstance(message, int):
                return self._get_err_msg(message)

            return message
        except IndexError:
            return self._get_err_msg(getattr(self, "error_code", None))

    @property
    def json(self):
        """Get any specific extra JSON keys to insert
        on the error response."""
        return self.args[1]


class BadRequest(LitecordError):
    status_code = 400


class Unauthorized(LitecordError):
    status_code = 401


class Forbidden(LitecordError):
    status_code = 403


class ForbiddenDM(Forbidden):
    error_code = 50007


class NotFound(LitecordError):
    status_code = 404


class GuildNotFound(NotFound):
    error_code = 10004


class ChannelNotFound(NotFound):
    error_code = 10003


class MessageNotFound(NotFound):
    error_code = 10008


class WebhookNotFound(NotFound):
    error_code = 10015


class UserNotFound(NotFound):
    error_code = 10013


class Ratelimited(LitecordError):
    status_code = 429


class MissingPermissions(Forbidden):
    error_code = 50013


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
