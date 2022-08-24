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
import earl

from litecord.json import LitecordJSONEncoder


def encode_json(payload) -> str:
    """Encode a given payload to JSON."""
    return json.dumps(payload, separators=(",", ":"), cls=LitecordJSONEncoder)


def decode_json(data: str):
    """Decode from JSON."""
    return json.loads(data)


def encode_etf(payload) -> str:
    """Encode a payload to ETF (External Term Format).

    This gives a JSON pass on the given payload (via calling encode_json and
    then decode_json) because we may want to encode objects that can only be
    encoded by LitecordJSONEncoder.

    Earl-ETF does not give the same interface for extensibility, hence why we
    do the pass.
    """
    sanitized = encode_json(payload)
    sanitized = decode_json(sanitized)
    return earl.pack(sanitized)


def _etf_decode_dict(data):
    """Decode a given dictionary."""
    # NOTE: this is very slow.

    if isinstance(data, bytes):
        return data.decode()

    if not isinstance(data, dict):
        return data

    _copy = dict(data)
    result = {}

    for key in _copy.keys():
        # assuming key is bytes rn.
        new_k = key.decode()

        # maybe nested dicts, so...
        result[new_k] = _etf_decode_dict(data[key])

    return result


def decode_etf(data: bytes):
    """Decode data in ETF to any."""
    res = earl.unpack(data)

    if isinstance(res, bytes):
        return data.decode()

    if isinstance(res, dict):
        return _etf_decode_dict(res)

    return res
