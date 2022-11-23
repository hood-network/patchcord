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

from litecord.common.users import create_user, delete_user
from litecord.blueprints.auth import make_token
from litecord.enums import UserFlags
from litecord.auth import hash_data


async def find_user(username, discriminator, ctx) -> int:
    """Get a user ID via the username/discrim pair."""
    return await ctx.db.fetchval(
        """
    SELECT id
    FROM users
    WHERE username = $1 AND discriminator = $2
    """,
        username,
        discriminator,
    )


async def set_any_user_flag(ctx, user_id, flag_name):
    old_flags = await ctx.db.fetchval(
        """
        SELECT flags
        FROM users
        WHERE id = $1
        """,
        user_id,
    )

    new_flags = old_flags | getattr(UserFlags, flag_name)

    await ctx.db.execute(
        """
        UPDATE users
        SET flags=$1
        WHERE id = $2
        """,
        new_flags,
        user_id,
    )


async def unset_any_user_flag(ctx, user_id, flag_name):
    old_flags = await ctx.db.fetchval(
        """
        SELECT flags
        FROM users
        WHERE id = $1
        """,
        user_id,
    )

    new_flags = old_flags ^ getattr(UserFlags, flag_name)

    await ctx.db.execute(
        """
        UPDATE users
        SET flags=$1
        WHERE id = $2
        """,
        new_flags,
        user_id,
    )


async def adduser(ctx, args):
    """Create a single user."""
    uid, _ = await create_user(args.username, args.email, args.password)

    user = await ctx.storage.get_user(uid)

    print("Created!")
    print(f"\tID: {uid}")
    print(f'\tUsername: {user["username"]}')
    print(f'\tDiscriminator: {user["discriminator"]}')


async def addbot(ctx, args):
    uid, _ = await create_user(args.username, args.email, args.password)

    await ctx.db.execute(
        """
        UPDATE users
        SET bot=True
        WHERE id = $1
        """,
        uid,
    )

    args.user_id = uid

    return await generate_bot_token(ctx, args)


async def set_flag(ctx, args):
    """Setting a 'staff' flag gives the user access to the Admin API.
    Beware of that.

    Flag changes only apply to a user after a server restart so that
    all connected clients get to refresh their state.
    """
    uid = await find_user(args.username, args.discriminator, ctx)

    if not uid:
        return print("user not found")

    await set_any_user_flag(ctx, uid, args.flag_name)
    print(f"Set {args.flag_name}")


async def unset_flag(ctx, args):
    """Unsetting a 'staff' flag revokes the user's access to the Admin API.

    Flag changes only apply to a user after a server restart so that
    all connected clients get to refresh their state.
    """
    uid = await find_user(args.username, args.discriminator, ctx)

    if not uid:
        return print("User not found")

    await unset_any_user_flag(ctx, uid, args.flag_name)
    print(f"Unset {args.flag_name}")


async def generate_bot_token(ctx, args):
    """Generate a token for a specified user."""

    password_hash = await ctx.db.fetchval(
        """
    SELECT password_hash
    FROM users
    WHERE id = $1
    """,
        int(args.user_id),
    )

    if not password_hash:
        print("User not found")
        return 1

    print(make_token(args.user_id, password_hash))


async def del_user(ctx, args):
    """Delete a user."""
    uid = await find_user(args.username, args.discriminator, ctx)

    if uid is None:
        print("User not found")
        return

    user = await ctx.storage.get_user(uid)

    print(f'\tID: {user["id"]}')
    print(f'\tUsername: {user["username"]}')
    print(f'\tDiscriminator: {user["discriminator"]}')

    print("\n Are you sure you want to delete this user? (y/n)")
    confirm = input()

    if confirm.lower() != "y":
        print("Aborted")
        return

    # we don't have pubsub context in the manage process to send update events
    await delete_user(uid, mass_update=False)
    print("Deleted user")


async def set_password_user(ctx, args):
    """set a user's password."""
    uid = await find_user(args.username, args.discriminator, ctx)
    if uid is None:
        print("User not found")
        return

    new_hash = await hash_data(args.password, loop=ctx.loop)
    await ctx.db.execute(
        """
        UPDATE users
        SET password_hash = $1
        WHERE id = $2
        """,
        new_hash,
        uid,
    )
    print("Set password")


async def permanent_nitro(ctx, args):
    """Give a user permanent nitro."""
    uid = await find_user(args.username, args.discriminator, ctx)
    if uid is None:
        print("User not found")
        return

    await ctx.db.execute(
        """
        UPDATE users
        SET premium_since = '2022-07-12 17:32:02'
        WHERE id = $1
        """,
        uid,
    )

    payment_source = ctx.winter_factory.snowflake()
    await ctx.db.execute(
        """
        INSERT into user_payment_sources
            (id, user_id, source_type, invalid, default_, expires_month, expires_year, brand, cc_full, paypal_email, billing_address)
        VALUES
            ($1, $2, 1, false, true, 1, 2038, 'visa', '4242424242424242', 'john.doe@mail.com', '{"city":"Washington","name":"John Doe","state":"DC","line_1":"1 Nonexistent Lane","line_2":"","country":"US","postal_code":"98001"}')
        """,
        payment_source,
        uid,
    )

    subscription = ctx.winter_factory.snowflake()
    await ctx.db.execute(
        """
        INSERT into user_subscriptions
            (id, source_id, user_id, s_type, payment_gateway, payment_gateway_plan_id, status, canceled_at, period_start, period_end)
        VALUES
            ($1, $2, $3, 1, 1, 'premium_year_tier_2', 1, NULL, '2022-07-12 17:32:02', '2038-01-01 01:00:00')
        """,
        subscription,
        payment_source,
        uid,
    )

    invoice = ctx.winter_factory.snowflake()
    await ctx.db.execute(
        """
        INSERT into user_payments
            (id, source_id, subscription_id, user_id, currency, status, amount, tax, tax_inclusive)
        VALUES
            ($1, $2, $3, $4, 'usd', 1, 9999, 0, true)
        """,
        invoice,
        payment_source,
        subscription,
        uid,
    )

    print("Permanent nitro granted")


def setup(subparser):
    setup_test_parser = subparser.add_parser("adduser", help="Create a user")
    setup_test_parser.add_argument("username", help="Username of the user")
    setup_test_parser.add_argument("email", help="Email of the user")
    setup_test_parser.add_argument("password", help="Password of the user")
    setup_test_parser.set_defaults(func=adduser)

    addbot_parser = subparser.add_parser("addbot", help="Create a bot")
    addbot_parser.add_argument("username", help="Username of the bot")
    addbot_parser.add_argument("email", help="Email of the bot")
    addbot_parser.add_argument("password", help="Password of the bot")
    addbot_parser.set_defaults(func=addbot)

    setflag_parser = subparser.add_parser("setflag", help="Set a flag for a user", description=set_flag.__doc__)
    setflag_parser.add_argument("username", help="Username of the user")
    setflag_parser.add_argument("discriminator", help="Discriminator of the user")
    setflag_parser.add_argument("flag_name", help="The flag to set"),
    setflag_parser.set_defaults(func=set_flag)

    unsetflag_parser = subparser.add_parser("unsetflag", help="Unset a flag for a user", description=unset_flag.__doc__)
    unsetflag_parser.add_argument("username", help="Username of the user")
    unsetflag_parser.add_argument("discriminator", help="Discriminator of the user")
    unsetflag_parser.add_argument("flag_name", help="The flag to unset"),
    unsetflag_parser.set_defaults(func=unset_flag)

    del_user_parser = subparser.add_parser("deluser", help="Delete a single user")
    del_user_parser.add_argument("username", help="Username of the user")
    del_user_parser.add_argument("discriminator", help="Discriminator of the user")
    del_user_parser.set_defaults(func=del_user)

    token_parser = subparser.add_parser(
        "gentoken",
        help="Generate a token for a specified user",
        description=generate_bot_token.__doc__,
    )
    token_parser.add_argument("user_id", help="ID of the user")
    token_parser.set_defaults(func=generate_bot_token)

    set_password_user_parser = subparser.add_parser("setpass", help="Set the password of a user")
    set_password_user_parser.add_argument("username", help="Username of the user")
    set_password_user_parser.add_argument("discriminator", help="Discriminator of the user")
    set_password_user_parser.add_argument("password", help="New password for the user")
    set_password_user_parser.set_defaults(func=set_password_user)

    nitro_parser = subparser.add_parser("addnitro", help="Give a user permanent nitro")
    nitro_parser.add_argument("username", help="Username of the user")
    nitro_parser.add_argument("discriminator", help="Discriminator of the user")
    nitro_parser.set_defaults(func=permanent_nitro)
