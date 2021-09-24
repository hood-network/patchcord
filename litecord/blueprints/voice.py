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
from collections import Counter
from random import choice

from quart import Blueprint, jsonify, current_app as app

from litecord.blueprints.auth import token_check

bp = Blueprint("voice", __name__)


def _majority_region_count(regions: list) -> str:
    """Return the first most common element in a given list."""
    counter = Counter(regions)
    common = counter.most_common(1)
    region, _count = common[0]

    return region


async def _choose_random_region() -> Optional[str]:
    """Give a random voice region."""
    regions = await app.db.fetch(
        """
    SELECT id
    FROM voice_regions
    """
    )

    regions = [r["id"] for r in regions]

    if not regions:
        return None

    return choice(regions)


async def _majority_region_any(user_id) -> Optional[str]:
    """Calculate the most likely region to make the user happy, but
    this is based on the guilds the user is IN, instead of the guilds
    the user owns."""
    guilds = await app.user_storage.get_user_guilds(user_id)

    if not guilds:
        return await _choose_random_region()

    res = []

    for guild_id in guilds:
        region = await app.db.fetchval(
            """
        SELECT region
        FROM guilds
        WHERE id = $1
        """,
            guild_id,
        )

        res.append(region)

    most_common = _majority_region_count(res)

    if most_common is None:
        return await _choose_random_region()

    return most_common


async def majority_region(user_id: int) -> Optional[str]:
    """Given a user ID, give the most likely region for the user to be
    happy with."""
    regions = await app.db.fetch(
        """
    SELECT region
    FROM guilds
    WHERE owner_id = $1
    """,
        user_id,
    )

    if not regions:
        return await _majority_region_any(user_id)

    regions = [r["region"] for r in regions]
    return _majority_region_count(regions)


async def _all_regions():
    user_id = await token_check()

    best_region = await majority_region(user_id)
    regions = await app.storage.all_voice_regions()

    for region in regions:
        region["optimal"] = region["id"] == best_region

    return jsonify(regions)


@bp.route("/regions", methods=["GET"])
async def voice_regions():
    """Return voice regions."""
    return await _all_regions()


@bp.route("/guilds/<int:guild_id>/regions", methods=["GET"])
async def guild_voice_regions():
    """Return voice regions."""
    # we return the same list as the normal /regions route on purpose.
    return await _all_regions()
