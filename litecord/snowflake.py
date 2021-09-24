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
snowflake.py - snowflake helper functions

    These functions generate discord-like snowflakes.
    File brought in from
        litecord-reference(https://github.com/lnmds/litecord-reference)
"""
import time
import datetime

# encoded in ms
EPOCH = 1420070400000

# internal state
_generated_ids = 0
PROCESS_ID = 1
WORKER_ID = 1

Snowflake = int


def _snowflake(timestamp: int) -> Snowflake:
    """Get a snowflake from a specific timestamp

    This function relies on modifying internal variables
    to generate unique snowflakes. Because of that every call
    to this function will generate a different snowflake,
    even with the same timestamp.

    Arguments
    ---------
    timestamp: int
        Timestamp to be feed in to the snowflake algorithm.
        This timestamp has to be an UNIX timestamp
         with millisecond precision.
    """
    # Yes, using global variables aren't the best idea
    # Maybe we could distribute the work of snowflake generation
    # to actually separated servers? :thinking:
    global _generated_ids

    # bits 0-12 encode _generated_ids (size 12)

    # modulo'd to prevent overflows
    genid_b = "{0:012b}".format(_generated_ids % 4096)

    # bits 12-17 encode PROCESS_ID (size 5)
    procid_b = "{0:05b}".format(PROCESS_ID)

    # bits 17-22 encode WORKER_ID (size 5)
    workid_b = "{0:05b}".format(WORKER_ID)

    # bits 22-64 encode (timestamp - EPOCH) (size 42)
    epochized = timestamp - EPOCH
    epoch_b = "{0:042b}".format(epochized)

    snowflake_b = f"{epoch_b}{workid_b}{procid_b}{genid_b}"
    _generated_ids += 1

    return int(snowflake_b, 2)


def snowflake_time(snowflake: Snowflake) -> float:
    """Get the UNIX timestamp(with millisecond precision, as a float)
    from a specific snowflake.
    """

    # the total size for a snowflake is 64 bits,
    # considering it is a string, position 0 to 42 will give us
    # the `epochized` variable
    snowflake_b = "{0:064b}".format(snowflake)
    epochized_b = snowflake_b[:42]
    epochized = int(epochized_b, 2)

    # since epochized is the time *since* the EPOCH
    # the unix timestamp will be the time *plus* the EPOCH
    timestamp = epochized + EPOCH

    # convert it to seconds
    # since we don't want to break the entire
    # snowflake interface
    return timestamp / 1000


def snowflake_datetime(snowflake: Snowflake) -> datetime.datetime:
    """Return a datetime object representing the snowflake."""
    unix_ts = snowflake_time(snowflake)
    return datetime.datetime.fromtimestamp(unix_ts)


def get_snowflake():
    """Generate a snowflake"""
    return _snowflake(int(time.time() * 1000))
