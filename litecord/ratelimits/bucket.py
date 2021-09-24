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

"""
main litecord ratelimiting code

    This code was copied from elixire's ratelimiting,
    which in turn is a work on top of discord.py's ratelimiting.
"""
import time


class RatelimitBucket:
    """Main ratelimit bucket class."""

    def __init__(self, tokens, second):
        self.requests = tokens
        self.second = second

        self._window = 0.0
        self._tokens = self.requests
        self.retries = 0
        self._last = 0.0

    def get_tokens(self, current):
        """Get the current amount of available tokens."""
        if not current:
            current = time.time()

        # by default, use _tokens
        tokens = self._tokens

        # if current timestamp is above _window + seconds
        # reset tokens to self.requests (default)
        if current > self._window + self.second:
            tokens = self.requests

        return tokens

    def update_rate_limit(self):
        """Update current ratelimit state."""
        current = time.time()
        self._last = current
        self._tokens = self.get_tokens(current)

        # we are using the ratelimit for the first time
        # so set current ratelimit window to right now
        if self._tokens == self.requests:
            self._window = current

        # Are we currently ratelimited?
        if self._tokens == 0:
            self.retries += 1
            return self.second - (current - self._window)

        # if not ratelimited, remove a token
        self.retries = 0
        self._tokens -= 1

        # if we got ratelimited after that token removal,
        # set window to now
        if self._tokens == 0:
            self._window = current

    def reset(self):
        """Reset current ratelimit to default state."""
        self._tokens = self.requests
        self._last = 0.0
        self.retries = 0

    def copy(self):
        """Create a copy of this ratelimit.

        Used to manage multiple ratelimits to users.
        """
        return RatelimitBucket(self.requests, self.second)

    def __repr__(self):
        return (
            f"<RatelimitBucket requests={self.requests} "
            f"second={self.second} window: {self._window} "
            f"tokens={self._tokens}>"
        )


class Ratelimit:
    """Manages buckets."""

    def __init__(self, tokens, second, keys=None):
        self._cache = {}
        if keys is None:
            keys = tuple()
        self.keys = keys
        self._cooldown = RatelimitBucket(tokens, second)

    def __repr__(self):
        return f"<Ratelimit cooldown={self._cooldown}>"

    def _verify_cache(self):
        current = time.time()
        dead_keys = [k for k, v in self._cache.items() if current > v._last + v.second]

        for k in dead_keys:
            del self._cache[k]

    def get_bucket(self, key) -> RatelimitBucket:
        if not self._cooldown:
            return None

        self._verify_cache()

        if key not in self._cache:
            bucket = self._cooldown.copy()
            self._cache[key] = bucket
        else:
            bucket = self._cache[key]

        return bucket
