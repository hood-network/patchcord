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

import json
from typing import Any
from decimal import Decimal
from uuid import UUID
from dataclasses import asdict, is_dataclass

import quart.json.provider


class LitecordJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder for Litecord. Useful for json.dumps"""

    def default(self, value: Any):
        if isinstance(value, (Decimal, UUID)):
            return str(value)

        if hasattr(value, "to_json"):
            return value.to_json()

        if is_dataclass(value):
            return asdict(value)

        return super().default(value)


class LitecordJSONProvider(quart.json.provider.DefaultJSONProvider):
    """Custom JSON provider for Quart."""

    def __init__(self, *args, **kwargs):
        self.encoder = LitecordJSONEncoder(**kwargs)

    def default(self, value: Any):
        self.encoder.default(value)


async def pg_set_json(con):
    """Set JSON and JSONB codecs for an asyncpg connection."""
    await con.set_type_codec(
        "json",
        encoder=lambda v: json.dumps(v, cls=LitecordJSONEncoder),
        decoder=json.loads,
        schema="pg_catalog",
    )

    await con.set_type_codec(
        "jsonb",
        encoder=lambda v: json.dumps(v, cls=LitecordJSONEncoder),
        decoder=json.loads,
        schema="pg_catalog",
    )
