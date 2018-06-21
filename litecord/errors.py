class LitecordError(Exception):
    status_code = 500

    @property
    def message(self):
        return self.args[0]


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


class WebsocketClose(Exception):
    @property
    def code(self):
        return self.args[0]

    @property
    def reason(self):
        return self.args[1]
