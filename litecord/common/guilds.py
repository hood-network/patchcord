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

from typing import List, TYPE_CHECKING
from logbook import Logger

from .messages import PLAN_ID_TO_TYPE


from ..permissions import get_role_perms, get_permissions, Target
from ..utils import dict_get, maybe_lazy_guild_dispatch
from ..enums import ChannelType, MessageType, NSFWLevel, PremiumType, UserFlags
from ..errors import BadRequest, Forbidden, MissingPermissions, NotFound
from litecord.common.interop import role_view
from litecord.pubsub.member import dispatch_member
from litecord.system_messages import send_sys_message

if TYPE_CHECKING:
    from litecord.typing_hax import app, request
else:
    from quart import current_app as app, request

log = Logger(__name__)


async def _check_max_guilds(user_id: int):
    plan_id = await app.db.fetchval(
        """
        SELECT payment_gateway_plan_id
        FROM user_subscriptions
        WHERE status = 1
        AND user_id = $1
        """,
        user_id,
    )
    premium_type = PLAN_ID_TO_TYPE.get(plan_id)
    guild_ids = await app.user_storage.get_user_guilds(user_id)
    max_guilds = 200 if premium_type == PremiumType.TIER_2 else 100
    if len(guild_ids) >= max_guilds:
        raise BadRequest(30001, max_guilds)


async def remove_member(guild_id: int, member_id: int, raise_err: bool = True) -> None:
    """Do common tasks related to deleting a member from the guild,
    such as dispatching GUILD_DELETE and GUILD_MEMBER_REMOVE."""
    owner_id = await app.db.fetchval(
        """
        SELECT owner_id
        FROM guilds
        WHERE id = $1
        """,
        guild_id,
    )
    if owner_id == member_id:
        raise MissingPermissions()

    res = await app.db.execute(
        """
        DELETE FROM members
        WHERE guild_id = $1 AND user_id = $2
        """,
        guild_id,
        member_id,
    )
    if res == "DELETE 0" and raise_err:
        raise NotFound(10007)
    elif res == "DELETE 0":
        return

    await dispatch_member(
        guild_id,
        member_id,
        ("GUILD_DELETE", {"guild_id": str(guild_id), "id": str(guild_id)}),
    )

    states, channels = await app.dispatcher.guild.unsub_user(guild_id, member_id)
    for channel_id in channels:
        for state in states:
            await app.dispatcher.channel.unsub(channel_id, state.session_id)

    await app.lazy_guild.remove_member(guild_id, member_id)
    await app.dispatcher.guild.dispatch(
        guild_id,
        (
            "GUILD_MEMBER_REMOVE",
            {"guild_id": str(guild_id), "user": {"id": member_id}},
        ),
    )


async def create_role(guild_id, name: str, **kwargs):
    """Create a role in a guild."""
    new_role_id = app.winter_factory.snowflake()

    everyone_perms = await get_role_perms(guild_id, guild_id)
    default_perms = dict_get(kwargs, "default_perms", everyone_perms.binary)

    # update all roles so that we have space for pos 1, but without
    # sending GUILD_ROLE_UPDATE for everyone
    await app.db.execute(
        """
    UPDATE roles
    SET
        position = position + 1
    WHERE guild_id = $1
      AND NOT (position = 0)
    """,
        guild_id,
    )

    await app.db.execute(
        """
        INSERT INTO roles (id, guild_id, name, color,
            hoist, position, permissions, managed, mentionable)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """,
        new_role_id,
        guild_id,
        name,
        dict_get(kwargs, "color", 0),
        dict_get(kwargs, "hoist", False),
        # always set ourselves on position 1
        1,
        int(dict_get(kwargs, "permissions", default_perms)),
        False,
        dict_get(kwargs, "mentionable", False),
    )

    role = await app.storage.get_role(new_role_id, guild_id)

    # we need to update the lazy guild handlers for the newly created group
    await maybe_lazy_guild_dispatch(guild_id, "new_role", role)

    await app.dispatcher.guild.dispatch(
        guild_id, ("GUILD_ROLE_CREATE", {"guild_id": str(guild_id), "role": role})
    )

    return role_view(role)


async def _specific_chan_create(channel_id, ctype, **kwargs):
    if ctype in (ChannelType.GUILD_TEXT, ChannelType.GUILD_NEWS):
        await app.db.execute(
            """
        INSERT INTO guild_text_channels (id, topic)
        VALUES ($1, $2)
        """,
            channel_id,
            kwargs.get("topic", ""),
        )
    elif ctype == ChannelType.GUILD_VOICE:
        await app.db.execute(
            """
            INSERT INTO guild_voice_channels (id, bitrate, user_limit)
            VALUES ($1, $2, $3)
            """,
            channel_id,
            kwargs.get("bitrate", 64),
            kwargs.get("user_limit", 0),
        )


async def _subscribe_users_new_channel(guild_id: int, channel_id: int) -> None:
    # for each state currently subscribed to guild, we check on the database
    # which states can also subscribe to the new channel at its creation.

    # the list of users that can subscribe are then used again for a pass
    # over the states and states that have user ids in that list become
    # subscribers of the new channel.
    users_to_sub: List[str] = []

    for session_id in app.dispatcher.guild.state[guild_id]:
        try:
            state = app.state_manager.fetch_raw(session_id)
        except KeyError:
            continue

        if state.user_id in users_to_sub:
            continue

        perms = await get_permissions(state.user_id, channel_id)
        if perms.bits.read_messages:
            users_to_sub.append(state.user_id)

    for session_id in app.dispatcher.guild.state[guild_id]:
        try:
            state = app.state_manager.fetch_raw(session_id)
        except KeyError:
            continue

        if state.user_id in users_to_sub:
            await app.dispatcher.channel.sub(channel_id, session_id)


async def create_guild_channel(
    guild_id: int, channel_id: int, ctype: ChannelType, **kwargs
):
    """Create a channel in a guild."""
    await app.db.execute(
        """
    INSERT INTO channels (id, channel_type)
    VALUES ($1, $2)
    """,
        channel_id,
        ctype.value,
    )

    # calc new pos
    max_pos = await app.db.fetchval(
        """
    SELECT MAX(position)
    FROM guild_channels
    WHERE guild_id = $1
    """,
        guild_id,
    )

    # account for the first channel in a guild too
    max_pos = max_pos or 0

    parent_id = kwargs.get("parent_id") or None

    banner = await app.icons.put(
        "channel_banner", channel_id, kwargs.get("banner"), always_icon=True
    )

    # all channels go to guild_channels
    await app.db.execute(
        """
    INSERT INTO guild_channels (id, guild_id, parent_id, name, position, banner)
    VALUES ($1, $2, $3, $4, $5, $6)
    """,
        channel_id,
        guild_id,
        parent_id,
        kwargs["name"],
        max_pos + 1,
        banner.icon_hash,
    )

    # the rest of sql magic is dependant on the channel
    # we're creating (a text or voice or category),
    # so we use this function.
    await _specific_chan_create(channel_id, ctype, **kwargs)

    await _subscribe_users_new_channel(guild_id, channel_id)

    # This needs to be last, because it depends on users being already sub'd
    if "permission_overwrites" in kwargs:
        await process_overwrites(
            guild_id, channel_id, kwargs["permission_overwrites"] or []
        )


async def _del_from_table(table: str, user_id: int):
    """Delete a row from a table."""
    res = await app.db.execute(
        f"""
    DELETE FROM {table}
    WHERE guild_id = $1
    """,
        user_id,
    )

    log.info("Deleting guild id {} from {}, res: {!r}", user_id, table, res)


async def delete_guild(guild_id: int):
    """Delete a single guild."""
    await _del_from_table("vanity_invites", guild_id)

    # while most guild channel tables have 'ON DELETE CASCADE', this
    # must not be true to the channels table, which is generic for any channel.
    for channel_id in await app.storage.get_channel_ids(guild_id):
        await app.db.execute(
            """
            DELETE FROM channels
            WHERE channels.id = $1
            """,
            channel_id,
        )

    res = await app.db.execute(
        """
    DELETE FROM guilds
    WHERE guilds.id = $1
    """,
        guild_id,
    )
    if res == "DELETE 0":
        raise NotFound(10004)

    # Discord's client expects IDs being string
    await app.dispatcher.guild.dispatch(
        guild_id,
        (
            "GUILD_DELETE",
            {
                "guild_id": str(guild_id),
                "id": str(guild_id),
                # 'unavailable': False,
            },
        ),
    )

    # remove from the dispatcher so nobody
    # becomes the little memer that tries to fuck up with
    # everybody's gateway
    await app.dispatcher.guild.drop(guild_id)


async def create_guild_settings(guild_id: int, user_id: int):
    """Create guild settings for the user
    joining the guild."""

    # new guild_settings are based off the currently
    # set guild settings (for the guild)
    m_notifs = await app.db.fetchval(
        """
    SELECT default_message_notifications
    FROM guilds
    WHERE id = $1
    """,
        guild_id,
    )

    await app.db.execute(
        """
    INSERT INTO guild_settings
        (user_id, guild_id, message_notifications)
    VALUES
        ($1, $2, $3)
    """,
        user_id,
        guild_id,
        m_notifs,
    )


async def add_member(
    guild_id: int, user_id: int, *, basic: bool = False, skip_check: bool = False
):
    """Add a user to a guild.

    If `basic` is set to true, side-effects from member adding won't be
    propagated.
    """

    if not skip_check:
        await _check_max_guilds(user_id)

        nsfw_level = await app.db.fetchval(
            """
        SELECT nsfw_level
        FROM guilds
        WHERE id = $1
        """,
            guild_id,
        )
        nsfw_level = NSFWLevel(nsfw_level or NSFWLevel.DEFAULT.value)

        features = await app.storage.guild_features(guild_id) or []
        user = await app.storage.get_user(user_id, True)

        if (
            "INTERNAL_EMPLOYEE_ONLY" in features
            and user["flags"] & UserFlags.staff != UserFlags.staff
        ):
            raise Forbidden(20017)

        if "INVITES_DISABLED" in features:
            raise Forbidden(40008)

        if (
            nsfw_level in (NSFWLevel.RESTRICTED, NSFWLevel.EXPLICIT)
            and not user["nsfw_allowed"]
        ):
            raise Forbidden(20024)

    await app.db.execute(
        """
        INSERT INTO members (user_id, guild_id)
        VALUES ($1, $2)
        """,
        user_id,
        guild_id,
    )

    await create_guild_settings(guild_id, user_id)

    if basic:
        return

    await app.db.execute(
        """
    INSERT INTO member_roles (user_id, guild_id, role_id)
    VALUES ($1, $2, $3)
    """,
        user_id,
        guild_id,
        guild_id,
    )

    system_channel_id = await app.db.fetchval(
        """
        SELECT system_channel_id FROM guilds
        WHERE id = $1
        """,
        guild_id,
    )
    if system_channel_id:
        await send_sys_message(
            system_channel_id, MessageType.GUILD_MEMBER_JOIN, user_id
        )

    # tell current members a new member came up
    member = await app.storage.get_member(guild_id, user_id)
    await app.dispatcher.guild.dispatch(
        guild_id, ("GUILD_MEMBER_ADD", {**member, **{"guild_id": str(guild_id)}})
    )

    # pubsub changes for new member
    await app.lazy_guild.new_member(guild_id, user_id)

    # TODO how to remove repetition between this and websocket's subscribe_all?
    states, channels = await app.dispatcher.guild.sub_user(guild_id, user_id)
    for channel_id in channels:
        for state in states:
            await app.dispatcher.channel.sub(channel_id, state.session_id)

    guild = await app.storage.get_guild_full(guild_id, user_id, 250)
    for state in states:
        await state.dispatch("GUILD_CREATE", guild)


async def _dispatch_action(guild_id: int, channel_id: int, user_id: int, perms) -> None:
    """Apply an action of sub/unsub to all states of a user."""
    states = app.state_manager.fetch_states(user_id, guild_id)
    for state in states:
        if perms.bits.read_messages:
            await app.dispatcher.channel.sub(channel_id, state.session_id)
        else:
            await app.dispatcher.channel.unsub(channel_id, state.session_id)


async def process_overwrites(guild_id: int, channel_id: int, overwrites: list) -> None:
    # user_ids serves as a "prospect" user id list.
    # for each overwrite we apply, we fill this list with user ids we
    # want to check later to subscribe/unsubscribe from the channel.
    # (users without read_messages are automatically unsubbed since we
    #  don't want to leak messages to them when they dont have perms anymore)

    # the expensiveness of large overwrite/role chains shines here.
    # since each user id we fill in implies an entire get_permissions call
    # (because we don't have the answer if a user is to be subbed/unsubbed
    #  with only overwrites, an overwrite for a user allowing them might be
    #  overwritten by a role overwrite denying them if they have the role),
    # we get a lot of tension on that, causing channel updates to lag a bit.

    # there may be some good optimizations to do here, such as doing some
    # precalculations like fetching get_permissions for everyone first, then
    # applying the new overwrites one by one, then subbing/unsubbing at the
    # end, but it would be very memory intensive.
    user_ids: List[int] = []

    for overwrite in overwrites:
        # 0 for role overwrite, 1 for member overwrite
        try:
            target_type = int(overwrite["type"])
        except Exception:
            target_type = 0 if overwrite["type"] == "role" else 1
        target_user = None if target_type == 0 else overwrite["id"]
        target_role = overwrite["id"] if target_type == 0 else None

        val = None
        if target_type == 0:
            val = await app.db.fetchval(
                """
            SELECT id
            FROM roles
            WHERE guild_id = $1 AND id = $2
            """,
                guild_id,
                target_role,
            )
        elif target_type == 1:
            val = await app.db.fetchval(
                """
            SELECT id
            FROM members
            WHERE id = $1 AND guild_id = $2
            """,
                target_user,
                guild_id,
            )
        if not val:
            raise NotFound(10009)

        target = Target(target_type, target_user, target_role)

        col_name = "target_user" if target.is_user else "target_role"
        constraint_name = f"channel_overwrites_{col_name}_uniq"

        await app.db.execute(
            f"""
            INSERT INTO channel_overwrites
                (guild_id, channel_id, target_type, target_role,
                target_user, allow, deny)
            VALUES
                ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT ON CONSTRAINT {constraint_name}
            DO
            UPDATE
                SET allow = $6, deny = $7
            """,
            guild_id,
            channel_id,
            target_type,
            target_role,
            target_user,
            overwrite["allow"],
            overwrite["deny"],
        )

        if target.is_user:
            assert target.user_id is not None
            user_ids.append(target.user_id)

        elif target.is_role:
            assert target.role_id is not None
            user_ids.extend(await app.storage.get_role_members(target.role_id))

    for user_id in user_ids:
        perms = await get_permissions(user_id, channel_id)
        await _dispatch_action(guild_id, channel_id, user_id, perms)
