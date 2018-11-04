from litecord.ratelimits.bucket import Ratelimit

"""
REST:
        POST Message |  5/5s    | per-channel
      DELETE Message |  5/1s    | per-channel
 PUT/DELETE Reaction |  1/0.25s | per-channel
        PATCH Member |  10/10s  | per-guild
   PATCH Member Nick |  1/1s    | per-guild
      PATCH Username |  2/3600s | per-account
      |All Requests| |  50/1s   | per-account
WS:
     Gateway Connect |   1/5s   | per-account
     Presence Update |   5/60s  | per-session
 |All Sent Messages| | 120/60s  | per-session
"""

REACTION_BUCKET = Ratelimit(1, 0.25, ('channel_id'))

RATELIMITS = {
    'channel_messages.create_message': Ratelimit(5, 5, ('channel_id')),
    'channel_messages.delete_message': Ratelimit(5, 1, ('channel_id')),

    # all of those share the same bucket.
    'channel_reactions.add_reaction': REACTION_BUCKET,
    'channel_reactions.remove_own_reaction': REACTION_BUCKET,
    'channel_reactions.remove_user_reaction': REACTION_BUCKET,

    'guild_members.modify_guild_member': Ratelimit(10, 10, ('guild_id')),
    'guild_members.update_nickname': Ratelimit(1, 1, ('guild_id')),

    # this only applies to username.
    # 'users.patch_me': Ratelimit(2, 3600),

    '_ws.connect': Ratelimit(1, 5),
    '_ws.presence': Ratelimit(5, 60),
    '_ws.messages': Ratelimit(120, 60),
}

class RatelimitManager:
    """Manager for the bucket managers"""
    def __init__(self):
        self._ratelimiters = {}
        self.global_bucket = Ratelimit(1, 1)
        self._fill_rtl()

    def _fill_rtl(self):
        for path, rtl in RATELIMITS.items():
            self._ratelimiters[path] = rtl

    def get_ratelimit(self, key: str) -> Ratelimit:
        """Get the :class:`Ratelimit` instance for a given path."""
        return self._ratelimiters.get(key, self.global_bucket)
