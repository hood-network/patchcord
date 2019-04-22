
class GuildMemoryStore:
    """Store in-memory properties about guilds.

    I could have just used Redis... probably too overkill to add
    aioredis to the already long depedency list, plus, I don't need
    """
    def __init__(self):
        self._store = {}

    def get(self, guild_id: int, attribute: str, default=None):
        """get a key"""
        return self._store.get(f'{guild_id}:{attribute}', default)

    def set(self, guild_id: int, attribute: str, value):
        """set a key"""
        self._store[f'{guild_id}:{attribute}'] = value
