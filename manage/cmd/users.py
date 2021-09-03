"""

Litecord
Copyright (C) 2018-2019  Luna Mendes

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


async def find_user(username, discrim, ctx) -> int:
    """Get a user ID via the username/discrim pair."""
    return await ctx.db.fetchval(
        """
    SELECT id
    FROM users
    WHERE username = $1 AND discriminator = $2
    """,
        username,
        discrim,
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

    print("created!")
    print(f"\tuid: {uid}")
    print(f'\tusername: {user["username"]}')
    print(f'\tdiscrim: {user["discriminator"]}')


async def set_flag(ctx, args):
    """Setting a 'staff' flag gives the user access to the Admin API.
    Beware of that.

    Flag changes only apply to a user after a server restart so that
    all connected clients get to refresh their state.
    """
    uid = await find_user(args.username, args.discrim, ctx)

    if not uid:
        return print("user not found")

    await set_any_user_flag(ctx, uid, args.flag_name)
    print(f"OK: set {args.flag_name}")


async def unset_flag(ctx, args):
    """Unsetting a 'staff' flag revokes the user's access to the Admin API.

    Flag changes only apply to a user after a server restart so that
    all connected clients get to refresh their state.
    """
    uid = await find_user(args.username, args.discrim, ctx)

    if not uid:
        return print("user not found")

    await unset_any_user_flag(ctx, uid, args.flag_name)
    print(f"OK: unset {args.flag_name}")


async def generate_bot_token(ctx, args):
    """Generate a token for specified bot."""

    password_hash = await ctx.db.fetchval(
        """
    SELECT password_hash
    FROM users
    WHERE id = $1 AND bot = 'true'
    """,
        int(args.user_id),
    )

    if not password_hash:
        return print("cannot find a bot with specified id")

    print(make_token(args.user_id, password_hash))


async def del_user(ctx, args):
    """Delete a user."""
    uid = await find_user(args.username, args.discrim, ctx)

    if uid is None:
        print("user not found")
        return

    user = await ctx.storage.get_user(uid)

    print(f'\tuid: {user["user_id"]}')
    print(f'\tuname: {user["username"]}')
    print(f'\tdiscrim: {user["discriminator"]}')

    print("\n you sure you want to delete user? press Y (uppercase)")
    confirm = input()

    if confirm != "Y":
        print("not confirmed")
        return

    # we don't have pubsub context in the manage process to send update events
    await delete_user(uid, mass_update=False)
    print("ok")


async def set_password_user(ctx, args):
    """set a user's password."""
    uid = await find_user(args.username, args.discrim, ctx)
    if uid is None:
        print("user not found")
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
    print("ok")


def setup(subparser):
    setup_test_parser = subparser.add_parser("adduser", help="create a user")

    setup_test_parser.add_argument("username", help="username of the user")
    setup_test_parser.add_argument("email", help="email of the user")
    setup_test_parser.add_argument("password", help="password of the user")

    setup_test_parser.set_defaults(func=adduser)

    setflag_parser = subparser.add_parser(
        "setflag", help="set a flag for a user", description=set_flag.__doc__
    )
    setflag_parser.add_argument("username")
    setflag_parser.add_argument("discrim", help="the discriminator of the user")
    setflag_parser.add_argument("flag_name", help="flag to set"),

    setflag_parser.set_defaults(func=set_flag)

    unsetflag_parser = subparser.add_parser(
        "unsetflag", help="unset a flag for a user", description=unset_flag.__doc__
    )
    unsetflag_parser.add_argument("username")
    unsetflag_parser.add_argument("discrim", help="the discriminator of the user")
    unsetflag_parser.add_argument("flag_name", help="flag to unset"),

    unsetflag_parser.set_defaults(func=unset_flag)

    del_user_parser = subparser.add_parser("deluser", help="delete a single user")

    del_user_parser.add_argument("username")
    del_user_parser.add_argument("discrim")

    del_user_parser.set_defaults(func=del_user)

    token_parser = subparser.add_parser(
        "generate_token",
        help="generate a token for specified bot",
        description=generate_bot_token.__doc__,
    )

    token_parser.add_argument("user_id")

    token_parser.set_defaults(func=generate_bot_token)

    set_password_user_parser = subparser.add_parser(
        "setpass", help="set password for a user"
    )

    set_password_user_parser.add_argument("username")
    set_password_user_parser.add_argument("discrim")
    set_password_user_parser.add_argument("password")

    set_password_user_parser.set_defaults(func=set_password_user)
