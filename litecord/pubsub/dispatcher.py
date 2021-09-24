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

from typing import (
    List,
    Generic,
    TypeVar,
    Any,
    Callable,
    Dict,
    Set,
    Mapping,
    Iterable,
    Tuple,
)
from collections import defaultdict

from logbook import Logger

log = Logger(__name__)


K = TypeVar("K")
V = TypeVar("V")
F = TypeVar("F")
EventType = TypeVar("EventType")
DispatchType = TypeVar("DispatchType")
F_Map = Mapping[V, F]

GatewayEvent = Tuple[str, Any]

__all__ = ["Dispatcher", "DispatcherWithState", "GatewayEvent"]


class Dispatcher(Generic[K, V, EventType, DispatchType]):
    """Pub/Sub backend dispatcher.

    Classes must implement this protocol.
    """

    async def sub(self, key: K, identifier: V) -> None:
        """Subscribe a given identifier to a given key."""
        ...

    async def sub_many(self, key: K, identifier_list: Iterable[V]) -> None:
        for identifier in identifier_list:
            await self.sub(key, identifier)

    async def unsub(self, key: K, identifier: V) -> None:
        """Unsubscribe a given identifier to a given key."""
        ...

    async def dispatch(self, key: K, event: EventType) -> DispatchType:
        ...

    async def dispatch_many(self, keys: List[K], *args: Any, **kwargs: Any) -> None:
        log.info("MULTI DISPATCH in {!r}, {} keys", self, len(keys))
        for key in keys:
            await self.dispatch(key, *args, **kwargs)

    async def drop(self, key: K) -> None:
        """Drop a key."""
        ...

    async def clear(self, key: K) -> None:
        """Clear a key from the backend."""
        ...

    async def dispatch_filter(
        self, key: K, filter_function: Callable[[K], bool], event: EventType
    ) -> List[str]:
        """Selectively dispatch to the list of subscribers.

        Function must return a list of separate identifiers for composability.
        """
        ...


class DispatcherWithState(Dispatcher[K, V, EventType, DispatchType]):
    """Pub/Sub backend with a state dictionary.

    This class was made to decrease the amount
    of boilerplate code on Pub/Sub backends
    that have that dictionary.
    """

    def __init__(self):
        super().__init__()

        #: the default dict is to a set
        #  so we make sure someone calling sub()
        #  twice won't get 2x the events for the
        #  same channel.
        self.state: Dict[K, Set[V]] = defaultdict(set)

    async def sub(self, key: K, identifier: V):
        self.state[key].add(identifier)

    async def unsub(self, key: K, identifier: V):
        self.state[key].discard(identifier)

    async def reset(self, key: K):
        self.state[key] = set()

    async def drop(self, key: K):
        try:
            self.state.pop(key)
        except KeyError:
            pass
