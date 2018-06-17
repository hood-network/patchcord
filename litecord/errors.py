class LitecordError(Exception):
    status_code = 500

    @property
    def message(self):
        return self.args[0]


class AuthError(LitecordError):
    status_code = 403


class WebsocketClose(Exception):
    @property
    def code(self):
        return self.args[0]

    @property
    def reason(self):
        return self.args[1]
