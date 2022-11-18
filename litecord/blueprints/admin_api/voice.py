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

import asyncpg
from quart import Blueprint, jsonify
from logbook import Logger
from typing import TYPE_CHECKING
from litecord.auth import admin_check
from litecord.schemas import validate
from litecord.admin_schemas import VOICE_SERVER, VOICE_REGION
from litecord.errors import BadRequest

if TYPE_CHECKING:
    from litecord.typing_hax import app, request
else:
    from quart import current_app as app, request

log = Logger(__name__)
bp = Blueprint("voice_admin", __name__)


@bp.route("/regions/<region>", methods=["GET"])
async def get_region_servers(region):
    """Return a list of all servers for a region."""
    await admin_check()
    servers = await app.voice.voice_server_list(region)
    return jsonify(servers)


@bp.route("/regions", methods=["PUT"])
async def insert_new_region():
    """Create a voice region."""
    await admin_check()
    j = validate(await request.get_json(), VOICE_REGION)

    j["id"] = j["id"].lower()

    await app.db.execute(
        """
    INSERT INTO voice_regions (id, name, vip, deprecated, custom)
    VALUES ($1, $2, $3, $4, $5)
    """,
        j["id"],
        j["name"],
        j["vip"],
        j["deprecated"],
        j["custom"],
    )

    regions = await app.storage.all_voice_regions()
    region_count = len(regions)

    # if region count is 1, this is the first region to be created,
    # so we should update all guilds to that region
    if region_count == 1:
        res = await app.db.execute(
            """
        UPDATE guilds
        SET region = $1
        """,
            j["id"],
        )

        log.info("updating guilds to first voice region: {}", res)

    await app.voice.lvsp.refresh_regions()
    return jsonify(regions)


@bp.route("/regions/<region>/server", methods=["PUT"])
async def put_region_server(region):
    """Insert a voice server to a region"""
    await admin_check()
    j = validate(await request.get_json(), VOICE_SERVER)

    try:
        await app.db.execute(
            """
        INSERT INTO voice_servers (hostname, region_id)
        VALUES ($1, $2)
        """,
            j["hostname"],
            region,
        )
    except asyncpg.UniqueViolationError:
        raise BadRequest(message="voice server already exists with given hostname")

    return "", 204


@bp.route("/regions/<region>/deprecate", methods=["PUT"])
async def deprecate_region(region):
    """Deprecate a voice region."""
    await admin_check()

    # TODO: write this
    await app.voice.disable_region(region)

    await app.db.execute(
        """
    UPDATE voice_regions
    SET deprecated = true
    WHERE id = $1
    """,
        region,
    )

    return "", 204


async def guild_region_check():
    """Check all guilds for voice region inconsistencies.

    Since the voice migration caused all guilds.region columns
    to become NULL, we need to remove such NULLs if we have more
    than one region setup.
    """

    regions = await app.storage.all_voice_regions()

    if not regions:
        log.info("region check: no regions to move guilds to")
        return

    res = await app.db.execute(
        """
        UPDATE guilds
        SET region = (
            SELECT id
            FROM voice_regions
            OFFSET floor(random()*$1)
            LIMIT 1
        )
        WHERE region = NULL
        """,
        len(regions),
    )

    log.info("region check: updating guild.region=null: {!r}", res)
