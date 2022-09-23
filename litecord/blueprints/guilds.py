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

from typing import Any, Dict, Optional, List, Tuple

from quart import Blueprint, request, current_app as app, jsonify

from litecord.common.guilds import (
    create_role,
    create_guild_channel,
    delete_guild,
    add_member,
    _check_max_guilds,
)
from litecord.common.interop import guild_view

from ..auth import token_check

from ..enums import ChannelType
from ..schemas import (
    validate,
    GUILD_CREATE,
    GUILD_UPDATE,
    SEARCH_CHANNEL,
    VANITY_URL_PATCH,
    MFA_TOGGLE,
)
from .checks import guild_check, guild_owner_check, guild_perm_check
from litecord.utils import str_bool, to_update
from litecord.errors import BadRequest, ManualFormError, MissingAccess
from litecord.permissions import get_permissions

DEFAULT_EVERYONE_PERMS = 1071698660929

bp = Blueprint("guilds", __name__)


async def guild_create_roles_prep(guild_id: int, roles: list) -> dict:
    """Create roles in preparation in guild create."""
    # by reaching this point in the code that means
    # roles is not nullable, which means
    # roles has at least one element, so we can access safely.

    # the first member in the roles array
    # are patches to the @everyone role
    everyone_patches = roles[0]
    if everyone_patches.get("permissions") is not None:
        await app.db.execute(
            """
            UPDATE roles
            SET permissions = $1
            WHERE id = $2
            """,
            everyone_patches["permissions"] or 0,
            guild_id,
        )

    default_perms = (
        (everyone_patches["permissions"] or 0)
        if everyone_patches.get("permissions") is not None
        else DEFAULT_EVERYONE_PERMS
    )

    role_map = {}
    if everyone_patches.get("id") is not None:
        role_map[everyone_patches["id"]] = guild_id
    # from the 2nd and forward,
    # should be treated as new roles
    for role in roles[1:]:
        cr = await create_role(
            guild_id, role.pop("name"), default_perms=default_perms, **role
        )
        if role.get("id") is not None:
            role_map[role["id"]] = int(cr["id"])

    return role_map


async def guild_create_channels_prep(guild_id: int, channels: list) -> dict:
    """Create channels pre-guild create"""
    channel_map = {}
    for channel_raw in channels:
        channel_id = app.winter_factory.snowflake()
        ctype = ChannelType(channel_raw.pop("type"))

        if channel_raw.get("id") is not None:
            channel_map[channel_raw["id"]] = channel_id
        elif channel_raw.get("parent_id") is not None:
            if channel_raw["parent_id"] not in channel_map:
                channel_raw.pop("parent_id")
            else:
                channel_raw["parent_id"] = channel_map[channel_raw["parent_id"]]

        await create_guild_channel(guild_id, channel_id, ctype, **channel_raw)

    return channel_map


def sanitize_icon(icon: Optional[str]) -> Optional[str]:
    """Return sanitized version of the given icon.

    Defaults to a jpeg icon when the header isn't given.
    """
    if icon and icon.startswith("data"):
        return icon

    return f"data:image/jpeg;base64,{icon}" if icon else None


async def _general_guild_icon(scope: str, guild_id: int, icon: Optional[str], **kwargs):
    encoded = sanitize_icon(icon)

    icon_kwargs = {"always_icon": True}

    if "size" in kwargs:
        icon_kwargs["size"] = kwargs["size"]

    return await app.icons.put(scope, guild_id, encoded, **icon_kwargs)


async def put_guild_icon(guild_id: int, icon: Optional[str]):
    """Insert a guild icon on the icon database."""
    return await _general_guild_icon(
        "guild_icon", guild_id, icon, size=(1024, 1024), always_icon=True
    )


async def handle_search(guild_id: Optional[int], channel_id: Optional[int] = None):
    """Search messages in a guild."""
    user_id = await token_check()

    j: Dict[str, Any] = request.args.to_dict(flat=False)
    for k, v in j.items():
        if SEARCH_CHANNEL[k].get("type") != "list":
            j[k] = v[0] if v else v

    j = validate(j, SEARCH_CHANNEL)
    if channel_id:
        can_read = [channel_id]
    else:
        assert guild_id is not None
        can_read = await fetch_readable_channels(guild_id, user_id)

    extra = ""
    args = [guild_id, can_read, j["limit"], j["offset"]]
    if j.get("content"):
        extra += f" AND content ILIKE '%'||${len(args) + 1}||'%'"
        args.append(j["content"])
    if j.get("min_id"):
        extra += f" AND id > ${len(args) + 1}"
        args.append(j["min_id"])
    if j.get("max_id"):
        extra += f" AND id < ${len(args) + 1}"
        args.append(j["max_id"])
    if j.get("author_id"):
        extra += f"AND author_id = ANY(${len(args) + 1}::bigint[])"
        args.append(j["author_id"])
    if j.get("channel_id") and not channel_id:
        can_read = [channel for channel in j["channel_id"] if channel in can_read]
    if j.get("mentions"):
        extra += f" AND content = ANY(${len(args) + 1}::text[])"
        args.append(
            [f"%<@{id}>%" for id in j["mentions"]]
            + [f"%<@!{id}>%" for id in j["mentions"]]
        )
    if j.get("link_hostname"):
        extra += f" AND content = ANY(${len(args) + 1}::text[])"
        args.append(
            [f"%http://{hostname}%" for hostname in j["link_hostname"]]
            + [f"%https://{hostname}%" for hostname in j["link_hostname"]]
        )
    if j.get("embed_provider"):
        extra += f" AND embeds::text == ANY(${len(args) + 1}::text[])"
        args.append(
            ['%"provider": {"name": %s%' % provider for provider in j["embed_provider"]]
        )
    if j.get("embed_type"):
        extra += f" AND embeds::text == ANY(${len(args) + 1}::text[])"
        args.append(['%"type": %s%' % type for type in j["embed_type"]])
    if j.get("attachment_filename"):
        extra += f" AND (SELECT COUNT(*) FROM attachments WHERE attachments.message_id = id AND attachments.filename = ANY(${len(args) + 1}::text[])) > 0"
        args.append([f"%{filename}%" for filename in j["attachment_filename"]])
    if j.get("attachment_extension"):
        extra += f" AND (SELECT COUNT(*) FROM attachments WHERE attachments.message_id = id AND attachments.filename = ANY(${len(args) + 1}::text[])) > 0"
        args.append([f"%.{extension}" for extension in j["attachment_extension"]])
    if j["mention_everyone"] is not None:
        extra += f" AND mention_everyone = ${len(args) + 1}"
        args.append(j["mention_everyone"])
    if j["pinned"] is not None:
        extra += f" AND (SELECT COUNT(*) FROM channel_pins WHERE message_id = id) {'>' if j['pinned'] else '='} 0"
    if not j["include_nsfw"]:
        extra += " AND (SELECT nsfw FROM guild_channels WHERE id = channel_id) = false"
    for has in j.get("has", []):
        if has == "-embed":
            extra += " AND embeds IS '[]'"
        elif has == "embed":
            extra += " AND embeds IS NOT '[]'"
        if has == "-sticker":
            extra += " AND sticker_ids IS '[]'"
        elif has == "sticker":
            extra += " AND sticker_ids IS NOT '[]'"
        if has == "-link":
            extra += " AND content NOT ILIKE '%'||'http://'||'%' AND content NOT ILIKE '%'||'https://'||'%'"
        elif has == "link":
            extra += " AND (content ILIKE '%'||'http://'||'%' OR content ILIKE ''%'||'https://'||'%')"
        if has == "-file":
            extra += " AND (SELECT COUNT(*) FROM attachments WHERE message_id = id) = 0"
        elif has == "file":
            extra += " AND (SELECT COUNT(*) FROM attachments WHERE message_id = id) > 0"
        if has == "-image":
            extra += " AND (SELECT COUNT(*) FROM attachments WHERE message_id = id AND image IS TRUE) = 0 AND embeds::text NOT ILIKE '%'||'\"type\": \"image\"'||'%'"
        elif has == "image":
            extra += " AND ((SELECT COUNT(*) FROM attachments WHERE message_id = id AND image IS TRUE) > 0 OR embeds::text ILIKE '%'||'\"type\": \"image\"'||'%')"
        if has == "-video":
            extra += " AND (SELECT COUNT(*) FROM attachments WHERE message_id = id AND (filename ILIKE '%.mp4' OR filename ILIKE '%.webm' OR filename ILIKE '%.mov')) = 0 AND embeds::text NOT ILIKE '%'||'\"type\": \"video\"'||'%'"
        elif has == "video":
            extra += " AND ((SELECT COUNT(*) FROM attachments WHERE message_id = id AND (filename ILIKE '%.mp4' OR filename ILIKE '%.webm' OR filename ILIKE '%.mov')) > 0 OR embeds::text ILIKE '%'||'\"type\": \"video\"'||'%')"
        if has == "-sound":
            extra += " AND (SELECT COUNT(*) FROM attachments WHERE message_id = id AND (filename ILIKE '%.mp3' OR filename ILIKE '%.ogg' OR filename ILIKE '%.wav' OR filename ILIKE '%.flac')) = 0"
        elif has == "sound":
            extra += " AND (SELECT COUNT(*) FROM attachments WHERE message_id = id AND (filename ILIKE '%.mp3' OR filename ILIKE '%.ogg' OR filename ILIKE '%.wav' OR filename ILIKE '%.flac')) > 0"
    for author_type in j.get("author_type", []):
        if author_type == "-webhook":
            extra += " AND author_id IS NOT NULL"
        elif author_type == "webhook":
            extra += " AND author_id IS NULL"
        if author_type == "-bot":
            extra += " AND NOT ((SELECT bot FROM users WHERE id = author_id) = true)"
        elif author_type == "bot":
            extra += " AND (SELECT bot FROM users WHERE id = author_id) = true"
        if author_type == "-user":
            extra += " AND NOT ((SELECT bot FROM users WHERE id = author_id) = false)"
        elif author_type == "user":
            extra += " AND (SELECT bot FROM users WHERE id = author_id) = false"

    # we ignore sort_by because idk how to sort by relevance

    messages = await app.storage.get_messages(
        user_id=user_id,
        extra_clause=", COUNT(*) OVER() as total_results",
        where_clause=f"""
            WHERE guild_id = $1
            AND channel_id = ANY($2::bigint[])
            {extra}
            ORDER BY id {j["sort_order"]}
            LIMIT $3 OFFSET $4
        """,
        args=args,
    )

    results = 0 if not messages else messages[0]["total_results"]
    for row in messages:
        row["hit"] = True
        row.pop("total_results", None)

    return {
        "total_results": results,
        "messages": [[message] for message in messages],
        "analytics_id": "analytics",
    }


@bp.route("", methods=["POST"], strict_slashes=False)
async def create_guild():
    """Create a new guild, assigning
    the user creating it as the owner and
    making them join."""
    user_id = await token_check()
    guild_id = app.winter_factory.snowflake()
    guild, _ = await handle_guild_create(user_id, guild_id)
    return jsonify(guild), 201


async def handle_guild_create(
    user_id: int, guild_id: int, extra_j: Optional[dict] = None
) -> Tuple[dict, dict]:
    j = validate(await request.get_json(), GUILD_CREATE)
    extra_j = extra_j or {}

    await _check_max_guilds(user_id)

    if "icon" in j and j["icon"]:
        image = await put_guild_icon(guild_id, j["icon"])
        image = image.icon_hash
    else:
        image = None

    await app.db.execute(
        """
        INSERT INTO guilds (id, name, region, icon, owner_id,
            verification_level, default_message_notifications,
            explicit_content_filter, afk_timeout, features)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        """,
        guild_id,
        j["name"],
        "deprecated",
        image,
        user_id,
        j.get("verification_level") or 0,
        j.get("default_message_notifications") or 0,
        j.get("explicit_content_filter") or 0,
        j.get("afk_timeout") or 300,
        extra_j.get("features") or [],
    )

    await add_member(guild_id, user_id, basic=True)

    # create the default @everyone role (everyone has it by default,
    # so we don't insert that in the table)

    # we also don't use create_role because the id of the role
    # is the same as the id of the guild, and create_role
    # generates a newinter.
    await app.db.execute(
        """
    INSERT INTO roles (id, guild_id, name, position, permissions)
    VALUES ($1, $2, $3, $4, $5)
    """,
        guild_id,
        guild_id,
        "@everyone",
        0,
        DEFAULT_EVERYONE_PERMS,
    )

    # add the @everyone role to the guild creator
    await app.db.execute(
        """
    INSERT INTO member_roles (user_id, guild_id, role_id)
    VALUES ($1, $2, $3)
    """,
        user_id,
        guild_id,
        guild_id,
    )

    # create a single #general channel.
    general_id = guild_id

    await create_guild_channel(
        guild_id, general_id, ChannelType.GUILD_TEXT, name="general"
    )

    role_map = {}
    if j.get("roles"):
        role_map = await guild_create_roles_prep(guild_id, j["roles"])

    channel_map = {}
    if j.get("channels"):
        for channel in j["channels"]:
            for overwrite in channel.get("permission_overwrites", []):
                overwrite["id"] = role_map.get(overwrite["id"], overwrite["id"])
        channel_map = await guild_create_channels_prep(guild_id, j["channels"])

    if j.get("afk_channel_id") is not None:
        afk_channel_id = channel_map.get(j["afk_channel_id"])
        if afk_channel_id:
            await app.db.execute(
                """
            UPDATE guilds
            SET afk_channel_id = $1
            WHERE id = $2
            """,
                afk_channel_id,
                guild_id,
            )

    if j.get("system_channel_id") is not None:
        system_channel_id = channel_map.get(j["system_channel_id"])
        if system_channel_id:
            await app.db.execute(
                """
            UPDATE guilds
            SET system_channel_id = $1
            WHERE id = $2
            """,
                system_channel_id,
                guild_id,
            )

    guild = await app.storage.get_guild(guild_id, user_id)
    extra = await app.storage.get_guild_extra(
        guild_id, user_id, 250
    )  # large count doesnt matter here because itll always be false

    await app.dispatcher.guild.sub_user(guild_id, user_id)
    await app.dispatcher.guild.dispatch(guild_id, ("GUILD_CREATE", {**guild, **extra}))
    return guild_view(guild), extra


@bp.route("/<int:guild_id>", methods=["GET"])
async def get_guild(guild_id):
    """Get a single guilds' information."""
    user_id = await token_check()
    await guild_check(user_id, guild_id)

    guild = guild_view(await app.storage.get_guild(guild_id, user_id))
    if request.args.get("with_counts", type=str_bool):
        guild.update(await app.storage.get_guild_counts(guild_id))

    return jsonify(guild)


async def _guild_update_icon(scope: str, guild_id: int, icon: Optional[str], **kwargs):
    """Update icon."""
    new_icon = await app.icons.update(scope, guild_id, icon, always_icon=True, **kwargs)

    table = {
        "guild_icon": "icon",
        "guild_splash": "splash",
        "guild_banner": "banner",
        "guild_discovery_splash": "discovery_splash",
    }.get(scope, scope)

    await app.db.execute(
        f"""
    UPDATE guilds
    SET {table} = $1
    WHERE id = $2
    """,
        new_icon.icon_hash,
        guild_id,
    )


@bp.route("/<int:guild_id>", methods=["PATCH"])
async def _update_guild(guild_id):
    user_id = await token_check()

    await guild_check(user_id, guild_id)
    await guild_perm_check(user_id, guild_id, "manage_guild")

    return jsonify(await handle_guild_update(guild_id))


async def handle_guild_update(guild_id: int, check: bool = True):
    user_id = await token_check()
    j = validate(await request.get_json(), GUILD_UPDATE)

    if "owner_id" in j:
        if check:
            await guild_owner_check(user_id, guild_id)

        await app.db.execute(
            """
        UPDATE guilds
        SET owner_id = $1
        WHERE id = $2
        """,
            int(j["owner_id"]),
            guild_id,
        )

    if "name" in j:
        await app.db.execute(
            """
        UPDATE guilds
        SET name = $1
        WHERE id = $2
        """,
            j["name"],
            guild_id,
        )

    guild = await app.storage.get_guild(guild_id)

    if to_update(j, guild, "icon"):
        await _guild_update_icon("guild_icon", guild_id, j["icon"], size=(1024, 1024))

    if to_update(j, guild, "splash") and await app.storage.has_feature(
        guild_id, "INVITE_SPLASH"
    ):
        await _guild_update_icon("guild_splash", guild_id, j["splash"])

    if to_update(j, guild, "banner") and await app.storage.has_feature(
        guild_id, "BANNER"
    ):
        await _guild_update_icon("guild_banner", guild_id, j["banner"])

    if to_update(j, guild, "discovery_splash") and await app.storage.has_feature(
        guild_id, "DISCOVERABLE"
    ):
        await _guild_update_icon(
            "guild_discovery_splash", guild_id, j["discovery_splash"]
        )

    if "features" in j:
        features = await app.storage.guild_features(guild_id) or []

        for feature in ("COMMUNITY", "INVITES_DISABLED", "INTERNAL_EMPLOYEE_ONLY"):
            if feature in j["features"] and feature not in features:
                features.append(feature)
                if feature == "COMMUNITY":
                    features.append("NEWS")
            elif feature not in j["features"] and feature in features:
                features.remove(feature)
                if feature == "COMMUNITY":
                    features.remove("NEWS")

        await app.db.execute(
            """
            UPDATE guilds
            SET features = $1
            WHERE id = $2
            """,
            features or None,
            guild_id,
        )

    fields = [
        "verification_level",
        "default_message_notifications",
        "explicit_content_filter",
        "afk_timeout",
        "description",
        "preferred_locale",
        "premium_progress_bar_enabled",
        "nsfw_level",
    ]

    for field in [f for f in fields if f in j]:
        await app.db.execute(
            f"""
        UPDATE guilds
        SET {field} = $1
        WHERE id = $2
        """,
            j[field],
            guild_id,
        )

    channel_fields = [
        "afk_channel_id",
        "system_channel_id",
        "rules_channel_id",
        "public_updates_channel_id",
    ]
    for field in [f for f in channel_fields if f in j]:
        # setting to null should remove the link between the afk/sys/rules/public updates channel
        # to the guild.
        if j[field] is None:
            await app.db.execute(
                f"""
            UPDATE guilds
            SET {field} = NULL
            WHERE id = $1
            """,
                guild_id,
            )

            continue

        chan = await app.storage.get_channel(j[field])

        if j[field] in (1, "1"):
            default_channel_map = {
                "afk_channel_id": "Inactive",
                "system_channel_id": "updates",
                "rules_channel_id": "rules",
                "public_updates_channel_id": "moderator-only",
            }

            # TODO: permissinos

            chan_id = app.winter_factory.snowflake()
            await create_guild_channel(
                guild_id,
                chan_id,
                ChannelType.GUILD_TEXT
                if field != "afk_channel_id"
                else ChannelType.GUILD_VOICE,
                name=default_channel_map[field],
            )

            j[field] = chan_id

            chan = await app.storage.get_channel(chan_id)
            await app.dispatcher.guild.dispatch(guild_id, ("CHANNEL_CREATE", chan))

        elif chan["guild_id"] != str(guild_id):
            raise ManualFormError(
                **{field: {"code": "INVALID_CHANNEL", "message": "Channel is invalid."}}
            )

        elif chan is None:
            await app.db.execute(
                f"""
            UPDATE guilds
            SET {field} = NULL
            WHERE id = $1
            """,
                guild_id,
            )
            continue

        await app.db.execute(
            f"""
        UPDATE guilds
        SET {field} = $1
        WHERE id = $2
        """,
            int(j[field]),
            guild_id,
        )

    guild = await app.storage.get_guild(guild_id, user_id)
    extra = await app.storage.get_guild_extra(guild_id, user_id)
    await app.dispatcher.guild.dispatch(guild_id, ("GUILD_UPDATE", {**guild, **extra}))
    return guild_view(guild)


@bp.route("/<int:guild_id>", methods=["DELETE"])
@bp.route("/<int:guild_id>/delete", methods=["POST"])
async def delete_guild_handler(guild_id):
    """Delete a guild."""
    user_id = await token_check()
    await guild_owner_check(user_id, guild_id)
    await delete_guild(guild_id)
    return "", 204


async def fetch_readable_channels(guild_id: int, user_id: int) -> List[int]:
    """Fetch readable channel IDs."""
    channel_ids = await app.storage.get_channel_ids(guild_id)
    res = []

    for channel_id in channel_ids:
        perms = await get_permissions(user_id, channel_id)

        if perms.bits.read_messages:
            res.append(channel_id)

    return res


@bp.route("/<int:guild_id>/messages/search", methods=["GET"])
async def search_guild(guild_id):
    user_id = await token_check()
    await guild_check(user_id, guild_id)

    return await handle_search(guild_id)


@bp.route("/<int:guild_id>/vanity-url", methods=["GET"])
async def get_vanity_url(guild_id: int):
    """Get the vanity url of a guild."""
    user_id = await token_check()
    await guild_perm_check(user_id, guild_id, "manage_guild")

    inv_code = await app.storage.vanity_invite(guild_id)

    if inv_code is None:
        return jsonify({"code": None})

    return jsonify(await app.storage.get_invite(inv_code))


@bp.route("/<int:guild_id>/vanity-url", methods=["PATCH"])
async def change_vanity_url(guild_id: int):
    """Get the vanity url of a guild."""
    user_id = await token_check()

    if not await app.storage.has_feature(guild_id, "VANITY_URL"):
        raise MissingAccess()

    await guild_perm_check(user_id, guild_id, "manage_guild")

    j = validate(await request.get_json(), VANITY_URL_PATCH)
    inv_code = j["code"]

    # store old vanity in a variable to delete it from
    # invites table
    old_vanity = await app.storage.vanity_invite(guild_id)

    if old_vanity == inv_code:
        return jsonify(await app.storage.get_invite(inv_code))

    # this is sad because we don't really use the things
    # sql gives us, but i havent really found a way to put
    # multiple ON CONFLICT clauses so we could UPDATE when
    # guild_id_fkey fails but INSERT when code_fkey fails..
    inv = await app.storage.get_invite(inv_code)
    if inv:
        raise BadRequest(50020)

    # TODO: this is bad, what if a guild has no channels?
    # we should probably choose the first channel that has
    # @everyone read messages
    channels = await app.storage.get_channel_data(guild_id)
    channel_id = int(channels[0]["id"])

    # delete the old invite, insert new one
    await app.db.execute(
        """
    DELETE FROM invites
    WHERE code = $1
    """,
        old_vanity,
    )

    await app.db.execute(
        """
        INSERT INTO invites
            (code, guild_id, channel_id, inviter, max_uses,
            max_age, temporary)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        inv_code,
        guild_id,
        channel_id,
        user_id,
        0,
        0,
        False,
    )

    await app.db.execute(
        """
    INSERT INTO vanity_invites (guild_id, code)
    VALUES ($1, $2)
    ON CONFLICT ON CONSTRAINT vanity_invites_pkey DO
    UPDATE
        SET code = $2
        WHERE vanity_invites.guild_id = $1
    """,
        guild_id,
        inv_code,
    )

    return jsonify(await app.storage.get_invite(inv_code))


@bp.route("/<int:guild_id>/mfa", methods=["POST"])
async def toggle_mfa(guild_id: int):
    """Toggle a guild's MFA level. The value currently does nothing."""
    user_id = await token_check()
    await guild_owner_check(user_id, guild_id)

    j = validate(await request.get_json(), MFA_TOGGLE)

    guild = await app.storage.get_guild_full(guild_id, user_id)

    if guild["mfa_level"] != j["level"]:
        await app.db.execute(
            """
        UPDATE guilds
        SET mfa_level = $1
        WHERE id = $2
        """,
            j["level"],
            guild_id,
        )

        guild["mfa_level"] = j["level"]
        await app.dispatcher.guild.dispatch(guild_id, ("GUILD_UPDATE", guild))

    return "", 204


@bp.route("/<int:guild_id>/templates", methods=["GET"])
async def get_guild_templates(guild_id: int):
    """This is currently just a stub"""

    return jsonify([])
