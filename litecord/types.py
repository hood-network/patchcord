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

from typing import Optional

# size units
KILOBYTES = 1024

# time units
MINUTES = 60
HOURS = 60 * MINUTES


class Color:
    """Custom color class"""

    def __init__(self, val: int):
        self.blue = val & 255
        self.green = (val >> 8) & 255
        self.red = (val >> 16) & 255

    @property
    def value(self):
        """Give the actual RGB integer encoding this color."""
        return int("%02x%02x%02x" % (self.red, self.green, self.blue), 16)

    @property
    def to_json(self):
        return self.value

    def __int__(self):
        return self.value


def timestamp_(dt) -> Optional[str]:
    """safer version for dt.isoformat()"""
    return f"{dt.isoformat()}+00:00" if dt else None
