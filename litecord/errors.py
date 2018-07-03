class LitecordError(Exception):
    status_code = 500

    @property
    def message(self):
        try:
            return self.args[0]
        except IndexError:
            return repr(self)

    @property
    def json(self):
        return self.args[1]


class BadRequest(LitecordError):
    status_code = 400


class Unauthorized(LitecordError):
    status_code = 401


class Forbidden(LitecordError):
    status_code = 403


class NotFound(LitecordError):
    status_code = 404


class GuildNotFound(LitecordError):
    status_code = 404


class ChannelNotFound(LitecordError):
    status_code = 404


class MessageNotFound(LitecordError):
    status_code = 404


class WebsocketClose(Exception):
    @property
    def code(self):
        return self.args[0]

    @property
    def reason(self):
        return self.args[1]
