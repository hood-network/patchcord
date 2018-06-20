from litecord.errors import WebsocketClose


class UnknownOPCode(WebsocketClose):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # hacky solution to
        # decrease code repetition
        self.args = [4001, self.args[0]]


class DecodeError(WebsocketClose):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.args = [4002, self.args[0]]


class InvalidShard(WebsocketClose):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.args = [4010, self.args[0]]


class ShardingRequired(WebsocketClose):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.args = [4011, self.args[0]]
