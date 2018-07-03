import collections
from typing import Any

from logbook import Logger

log = Logger(__name__)


class EventDispatcher:
    """Pub/Sub routines for litecord."""
    def __init__(self, sm):
        self.state_manager = sm
        self.guild_buckets = collections.defaultdict(set)

    def sub_guild(self, guild_id: int, user_id: int):
        """Subscribe to a guild's events, given the user ID."""
        self.guild_buckets[guild_id].add(user_id)

    def unsub_guild(self, guild_id: int, user_id: int):
        """Unsubscribe from a guild, given user ID"""
        self.guild_buckets[guild_id].discard(user_id)

    def remove_guild(self, guild_id):
        """Reset the guild bucket."""
        self.guild_buckets[guild_id] = set()

    def sub_many(self, user_id: int, guild_ids: list):
        """Subscribe to many guilds at a time."""
        for guild_id in guild_ids:
            self.sub_guild(guild_id, user_id)

    async def dispatch_guild(self, guild_id: int,
                             event_name: str, event_payload: Any):
        """Dispatch an event to a guild"""
        users = self.guild_buckets[guild_id]
        dispatched = 0

        log.info('Dispatching {} {!r} to {} users',
                 guild_id, event_name, len(users))

        for user_id in set(users):
            # fetch all connections that are tied to the guild,
            # this includes all connections that are just a single shard
            # and all shards that are nicely working
            states = self.state_manager.fetch_states(user_id, guild_id)

            # if there are no more states tied to the guild,
            # why keep the user as a subscriber?
            if not states:
                self.unsub_guild(guild_id, user_id)
                continue

            # for each reasonable state/shard, dispatch event
            for state in states:
                # NOTE: maybe a separate task for that async?
                await state.ws.dispatch(event_name, event_payload)
                dispatched += 1

        log.info('Dispatched {} {!r} to {} states',
                 guild_id, event_name, dispatched)
