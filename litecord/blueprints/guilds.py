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

from typing import Optional, List

from quart import Blueprint, request, current_app as app, jsonify

from litecord.common.guilds import (
    create_role,
    create_guild_channel,
    delete_guild,
    add_member,
)

from ..auth import token_check

from ..enums import ChannelType
from ..schemas import (
    validate,
    GUILD_CREATE,
    GUILD_UPDATE,
    SEARCH_CHANNEL,
    VANITY_URL_PATCH,
)
from .checks import guild_check, guild_owner_check, guild_perm_check
from litecord.utils import to_update, search_result_from_list
from litecord.errors import BadRequest
from litecord.permissions import get_permissions

DEFAULT_EVERYONE_PERMS = 104324161

bp = Blueprint("guilds", __name__)


async def guild_create_roles_prep(guild_id: int, roles: list):
    """Create roles in preparation in guild create."""
    # by reaching this point in the code that means
    # roles is not nullable, which means
    # roles has at least one element, so we can access safely.

    # the first member in the roles array
    # are patches to the @everyone role
    everyone_patches = roles[0]
    for field in everyone_patches:
        await app.db.execute(
            f"""
        UPDATE roles
        SET {field}={everyone_patches[field]}
        WHERE roles.id = $1
        """,
            guild_id,
        )

    default_perms = everyone_patches.get("permissions") or DEFAULT_EVERYONE_PERMS

    # from the 2nd and forward,
    # should be treated as new roles
    for role in roles[1:]:
        await create_role(guild_id, role["name"], default_perms=default_perms, **role)


async def guild_create_channels_prep(guild_id: int, channels: list):
    """Create channels pre-guild create"""
    for channel_raw in channels:
        channel_id = app.winter_factory.snowflake()
        ctype = ChannelType(channel_raw["type"])

        await create_guild_channel(guild_id, channel_id, ctype)


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
    return await _general_guild_icon("guild", guild_id, icon, size=(128, 128))


@bp.route("", methods=["POST"], strict_slashes=False)
async def create_guild():
    """Create a new guild, assigning
    the user creating it as the owner and
    making them join."""
    user_id = await token_check()
    j = validate(await request.get_json(), GUILD_CREATE)

    guild_id = app.winter_factory.snowflake()

    if "icon" in j:
        image = await put_guild_icon(guild_id, j["icon"])
        image = image.icon_hash
    else:
        image = None

    region = j["region"] if "region" in j else next(iter(app.voice.lvsp.regions))

    await app.db.execute(
        """
        INSERT INTO guilds (id, name, region, icon, owner_id,
            verification_level, default_message_notifications,
            explicit_content_filter)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """,
        guild_id,
        j["name"],
        region,
        image,
        user_id,
        j.get("verification_level", 0),
        j.get("default_message_notifications", 0),
        j.get("explicit_content_filter", 0),
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
    general_id = app.winter_factory.snowflake()

    await create_guild_channel(
        guild_id, general_id, ChannelType.GUILD_TEXT, name="general"
    )

    if j.get("roles"):
        await guild_create_roles_prep(guild_id, j["roles"])

    if j.get("channels"):
        await guild_create_channels_prep(guild_id, j["channels"])

    guild_total = await app.storage.get_guild_full(guild_id, user_id, 250)

    await app.dispatcher.guild.sub_user(guild_id, user_id)

    await app.dispatcher.guild.dispatch(guild_id, ("GUILD_CREATE", guild_total))
    return jsonify(guild_total)


@bp.route("/<int:guild_id>", methods=["GET"])
async def get_guild(guild_id):
    """Get a single guilds' information."""
    user_id = await token_check()
    await guild_check(user_id, guild_id)

    return jsonify(await app.storage.get_guild_full(guild_id, user_id, 250))


async def _guild_update_icon(scope: str, guild_id: int, icon: Optional[str], **kwargs):
    """Update icon."""
    new_icon = await app.icons.update(scope, guild_id, icon, always_icon=True, **kwargs)

    table = {"guild": "icon"}.get(scope, scope)

    await app.db.execute(
        f"""
    UPDATE guilds
    SET {table} = $1
    WHERE id = $2
    """,
        new_icon.icon_hash,
        guild_id,
    )


async def _guild_update_region(guild_id, region):
    is_vip = region.vip
    can_vip = await app.storage.has_feature(guild_id, "VIP_REGIONS")

    if is_vip and not can_vip:
        raise BadRequest("can not assign guild to vip-only region")

    await app.db.execute(
        """
    UPDATE guilds
    SET region = $1
    WHERE id = $2
    """,
        region.id,
        guild_id,
    )


@bp.route("/<int:guild_id>", methods=["PATCH"])
async def _update_guild(guild_id):
    user_id = await token_check()

    await guild_check(user_id, guild_id)
    await guild_perm_check(user_id, guild_id, "manage_guild")
    j = validate(await request.get_json(), GUILD_UPDATE)

    if "owner_id" in j:
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

    if "region" in j:
        region = app.voice.lvsp.region(j["region"])

        if region is not None:
            await _guild_update_region(guild_id, region)

    # small guild to work with to_update()
    guild = await app.storage.get_guild(guild_id)

    if to_update(j, guild, "icon"):
        await _guild_update_icon("guild", guild_id, j["icon"], size=(128, 128))

    if to_update(j, guild, "splash"):
        if not await app.storage.has_feature(guild_id, "INVITE_SPLASH"):
            raise BadRequest("guild does not have INVITE_SPLASH feature")

        await _guild_update_icon("splash", guild_id, j["splash"])

    if to_update(j, guild, "banner"):
        if not await app.storage.has_feature(guild_id, "VERIFIED"):
            raise BadRequest("guild is not verified")

        await _guild_update_icon("banner", guild_id, j["banner"])

    if to_update(j, guild, "discovery_splash"):
        if not await app.storage.has_feature(guild_id, "PUBLIC"):
            raise BadRequest("guild does not have PUBLIC feature")

        await _guild_update_icon("discovery_splash", guild_id, j["discovery_splash"])

    fields = [
        "verification_level",
        "default_message_notifications",
        "explicit_content_filter",
        "afk_timeout",
        "description",
        "preferred_locale",
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

        if chan is None:
            raise BadRequest("invalid channel id")

        if chan["guild_id"] != str(guild_id):
            raise BadRequest("channel id not linked to guild")

        await app.db.execute(
            f"""
        UPDATE guilds
        SET {field} = $1
        WHERE id = $2
        """,
            int(j[field]),
            guild_id,
        )

    guild = await app.storage.get_guild_full(guild_id, user_id)
    await app.dispatcher.guild.dispatch(guild_id, ("GUILD_UPDATE", guild))
    return jsonify(guild)


@bp.route("/<int:guild_id>", methods=["DELETE"])
# this endpoint is not documented, but used by the official client.
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
async def search_messages(guild_id):
    """Search messages in a guild.

    This is an undocumented route.
    """
    user_id = await token_check()
    await guild_check(user_id, guild_id)

    j = validate(dict(request.args), SEARCH_CHANNEL)

    # instead of writing a function in pure sql (which would be
    # better/faster for this usecase), consdering that it would be
    # hard to write the function in the first place, we generate
    # a list of channels the user can read AHEAD of time, then
    # use that list on the main search query.
    can_read = await fetch_readable_channels(guild_id, user_id)

    rows = await app.db.fetch(
        """
    SELECT orig.id AS current_id,
        COUNT(*) OVER() as total_results,
        array((SELECT messages.id AS before_id
         FROM messages WHERE messages.id < orig.id
         ORDER BY messages.id DESC LIMIT 2)) AS before,
        array((SELECT messages.id AS after_id
         FROM messages WHERE messages.id > orig.id
         ORDER BY messages.id ASC LIMIT 2)) AS after

    FROM messages AS orig
    WHERE guild_id = $1
      AND orig.content LIKE '%'||$2||'%'
      AND ARRAY[orig.channel_id] <@ $4::bigint[]
    ORDER BY orig.id DESC
    LIMIT 50
    OFFSET $3
    """,
        guild_id,
        j["content"],
        j["offset"],
        can_read,
    )

    return jsonify(await search_result_from_list(rows))


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
        # TODO: is this the right error
        raise BadRequest("guild has no vanity url support")

    await guild_perm_check(user_id, guild_id, "manage_guild")

    j = validate(await request.get_json(), VANITY_URL_PATCH)
    inv_code = j["code"]

    # store old vanity in a variable to delete it from
    # invites table
    old_vanity = await app.storage.vanity_invite(guild_id)

    if old_vanity == inv_code:
        raise BadRequest("can not change to same invite")

    # this is sad because we don't really use the things
    # sql gives us, but i havent really found a way to put
    # multiple ON CONFLICT clauses so we could UPDATE when
    # guild_id_fkey fails but INSERT when code_fkey fails..
    inv = await app.storage.get_invite(inv_code)
    if inv:
        raise BadRequest("invite already exists")

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
        # sane defaults for vanity urls.
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


@bp.route("/<int:guild_id>/templates", methods=["GET"])
async def get_guild_templates(guild_id: int):
    """This is currently just a stub"""

    return jsonify([])
