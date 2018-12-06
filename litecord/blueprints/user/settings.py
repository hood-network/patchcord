from quart import Blueprint, jsonify, request, current_app as app

from litecord.auth import token_check
from litecord.schemas import validate, USER_SETTINGS, GUILD_SETTINGS
from litecord.blueprints.checks import guild_check

bp = Blueprint('users_settings', __name__)


@bp.route('/@me/settings', methods=['GET'])
async def get_user_settings():
    """Get the current user's settings."""
    user_id = await token_check()
    settings = await app.user_storage.get_user_settings(user_id)
    return jsonify(settings)


@bp.route('/@me/settings', methods=['PATCH'])
async def patch_current_settings():
    """Patch the users' current settings.

    More information on what settings exist
    is at Storage.get_user_settings and the schema.sql file.
    """
    user_id = await token_check()
    j = validate(await request.get_json(), USER_SETTINGS)

    json_fields = ['guild_positions', 'restricted_guilds']

    for key in j:
        val = j[key]
        jsonb_cnv = ''

        # force postgres to update to jsonb
        # when the fields ARE jsonb.
        if key in json_fields:
            jsonb_cnv = '::jsonb'

        await app.db.execute(f"""
        UPDATE user_settings
        SET {key}=$1{jsonb_cnv}
        WHERE id = $2
        """, val, user_id)

    settings = await app.user_storage.get_user_settings(user_id)
    await app.dispatcher.dispatch_user(
        user_id, 'USER_SETTINGS_UPDATE', settings)
    return jsonify(settings)


@bp.route('/@me/guilds/<int:guild_id>/settings', methods=['PATCH'])
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

    for field in (k for k in j.keys() if k != 'channel_overrides'):
        await app.db.execute(f"""
        UPDATE guild_settings
        SET {field} = $1
        WHERE user_id = $2 AND guild_id = $3
        """, j[field], user_id, guild_id)

    chan_ids = await app.storage.get_channel_ids(guild_id)

    for chandata in j.get('channel_overrides', {}).items():
        chan_id, chan_overrides = chandata
        chan_id = int(chan_id)

        # ignore channels that aren't in the guild.
        if chan_id not in chan_ids:
            continue

        for field in chan_overrides:
            await app.db.execute(f"""
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
            """, user_id, guild_id, chan_id, chan_overrides[field])

    settings = await app.user_storage.get_guild_settings_one(
        user_id, guild_id)

    await app.dispatcher.dispatch_user(
        user_id, 'USER_GUILD_SETTINGS_UPDATE', settings)

    return jsonify(settings)


@bp.route('/@me/notes/<int:target_id>', methods=['PUT'])
async def put_note(target_id: int):
    """Put a note to a user.

    This route is in this blueprint because I consider
    notes to be personalized settings, so.
    """
    user_id = await token_check()

    j = await request.get_json()
    note = str(j['note'])

    # UPSERTs are beautiful
    await app.db.execute("""
    INSERT INTO notes (user_id, target_id, note)
    VALUES ($1, $2, $3)

    ON CONFLICT ON CONSTRAINT notes_pkey
    DO UPDATE SET
        note = $3
    WHERE notes.user_id = $1
      AND notes.target_id = $2
    """, user_id, target_id, note)

    await app.dispatcher.dispatch_user(user_id, 'USER_NOTE_UPDATE', {
        'id': str(target_id),
        'note': note,
    })

    return '', 204

