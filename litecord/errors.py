class LitecordError(Exception):
    status_code = 500

    @property
    def message(self):
        return self.args[0]


class AuthError(LitecordError):
    status_code = 403
