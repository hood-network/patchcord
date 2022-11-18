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

from quart import Blueprint, jsonify
from typing import TYPE_CHECKING

from litecord.auth import token_check
from litecord.schemas import validate, USER_SETTINGS, GUILD_SETTINGS
from litecord.blueprints.checks import guild_check
from litecord.pubsub.user import dispatch_user
from litecord.errors import NotFound

if TYPE_CHECKING:
    from litecord.typing_hax import app, request
else:
    from quart import current_app as app, request

bp = Blueprint("users_settings", __name__)


@bp.route("/@me/settings", methods=["GET"])
async def get_user_settings():
    """Get the current user's settings."""
    user_id = await token_check()
    settings = await app.user_storage.get_user_settings(user_id)
    return jsonify(settings)


@bp.route("/@me/settings", methods=["PATCH"])
async def patch_current_settings():
    """Patch the users' current settings.

    More information on what settings exist
    is at Storage.get_user_settings and the schema.sql file.
    """
    user_id = await token_check()
    j = validate(await request.get_json(), USER_SETTINGS)

    for key in j:
        val = j[key]

        await app.storage.execute_with_json(
            f"""
        UPDATE user_settings
        SET {key}=$1
        WHERE id = $2
        """,
            val,
            user_id,
        )

    settings = await app.user_storage.get_user_settings(user_id)
    await dispatch_user(user_id, ("USER_SETTINGS_UPDATE", settings))
    return jsonify(settings)


# @bp.route("/@me/settings-proto/<int:proto>", methods=["GET", "PATCH"])
# async def settings_proto(proto: int):
#     """Proto settings stub"""
#     return jsonify({"settings": "CgIYAQ=="})


@bp.route("/@me/guilds/<int:guild_id>/settings", methods=["PATCH"])
async def patch_guild_settings(guild_id: int):
    """Update the users' guild settings for a given guild.

    Guild settings are usually related to notifications.
    """
    user_id = await token_check()
    await guild_check(user_id, guild_id)

    j = validate(await request.get_json(), GUILD_SETTINGS)

    # querying the guild settings information before modifying
    # will make sure they exist in the table.
    await app.user_storage.get_guild_settings_one(user_id, guild_id)

    for field in (k for k in j.keys() if k != "channel_overrides"):
        await app.db.execute(
            f"""
        UPDATE guild_settings
        SET {field} = $1
        WHERE user_id = $2 AND guild_id = $3
        """,
            j[field],
            user_id,
            guild_id,
        )

    chan_ids = await app.storage.get_channel_ids(guild_id)

    for chandata in j.get("channel_overrides", {}).items():
        chan_id, chan_overrides = chandata
        chan_id = int(chan_id)

        # ignore channels that aren't in the guild.
        if chan_id not in chan_ids:
            continue

        for field in chan_overrides:
            await app.db.execute(
                f"""
            INSERT INTO guild_settings_channel_overrides
                (user_id, guild_id, channel_id, {field})
            VALUES
                ($1, $2, $3, $4)
            ON CONFLICT
                ON CONSTRAINT guild_settings_channel_overrides_pkey
            DO
              UPDATE
                SET {field} = $4
                WHERE guild_settings_channel_overrides.user_id = $1
                  AND guild_settings_channel_overrides.guild_id = $2
                  AND guild_settings_channel_overrides.channel_id = $3
            """,
                user_id,
                guild_id,
                chan_id,
                chan_overrides[field],
            )

    settings = await app.user_storage.get_guild_settings_one(user_id, guild_id)

    await dispatch_user(user_id, ("USER_GUILD_SETTINGS_UPDATE", settings))

    return jsonify(settings)


@bp.route("/@me/notes", methods=["GET"])
async def get_notes():
    """Get all of a user's notes."""
    user_id = await token_check()
    notes = await app.db.fetch(
        """
        SELECT note, target_id::text
        FROM notes
        WHERE user_id = $1
        """,
        user_id,
    )

    return jsonify({n["target_id"]: n["note"] for n in notes})


@bp.route("/@me/notes/<int:target_id>", methods=["GET"])
async def get_note(target_id: int):
    """Get a single note from a user."""
    user_id = await token_check()
    note = await app.db.fetchval(
        """
        SELECT note
        FROM notes
        WHERE user_id = $1 AND target_id = $2
        """,
        user_id,
        target_id,
    )

    if note is None:
        raise NotFound(10013)

    return jsonify(
        {"user_id": str(user_id), "note_user_id": str(target_id), "note": note}
    )


@bp.route("/@me/notes/<int:target_id>", methods=["PUT"])
async def put_note(target_id: int):
    """Put a note to a user.

    This route is in this blueprint because I consider
    notes to be personalized settings, so.
    """
    user_id = await token_check()

    j = await request.get_json()
    note = str(j["note"])

    # UPSERTs are beautiful
    await app.db.execute(
        """
    INSERT INTO notes (user_id, target_id, note)
    VALUES ($1, $2, $3)

    ON CONFLICT ON CONSTRAINT notes_pkey
    DO UPDATE SET
        note = $3
    WHERE notes.user_id = $1
      AND notes.target_id = $2
    """,
        user_id,
        target_id,
        note,
    )

    await dispatch_user(
        user_id, ("USER_NOTE_UPDATE", {"id": str(target_id), "note": note})
    )

    return "", 204
