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

import base64
import itsdangerous
import bcrypt
from litecord.blueprints.auth import create_user, make_token
from litecord.blueprints.users import delete_user
from litecord.enums import UserFlags


async def find_user(username, discrim, ctx) -> int:
    """Get a user ID via the username/discrim pair."""
    return await ctx.db.fetchval("""
    SELECT id
    FROM users
    WHERE username = $1 AND discriminator = $2
    """, username, discrim)

async def set_user_staff(user_id, ctx):
    """Give a single user staff status."""
    old_flags = await ctx.db.fetchval("""
    SELECT flags
    FROM users
    WHERE id = $1
    """, user_id)

    new_flags = old_flags | UserFlags.staff

    await ctx.db.execute("""
    UPDATE users
    SET flags=$1
    WHERE id = $2
    """, new_flags, user_id)


async def adduser(ctx, args):
    """Create a single user."""
    uid, _ = await create_user(args.username, args.email,
                               args.password, ctx.db, ctx.loop)

    user = await ctx.storage.get_user(uid)

    print('created!')
    print(f'\tuid: {uid}')
    print(f'\tusername: {user["username"]}')
    print(f'\tdiscrim: {user["discriminator"]}')


async def make_staff(ctx, args):
    """Give a single user the staff flag.

    This will grant them access to the Admin API.

    The flag changes will only apply after a
    server restart.
    """
    uid = await find_user(args.username, args.discrim, ctx)

    if not uid:
        return print('user not found')

    await set_user_staff(uid, ctx)
    print('OK: set staff')

async def generate_bot_token(ctx, args):
    """Generate a token for specified bot."""

    password_hash = await ctx.db.fetchval("""
    SELECT password_hash
    FROM users
    WHERE id = $1 AND bot = 'true'
    """, int(args.user_id))

    if not password_hash:
        return print('cannot find a bot with specified id')

    print(make_token(args.user_id, password_hash))


async def del_user(ctx, args):
    """Delete a user."""
    uid = await find_user(args.username, args.discrim, ctx)

    if uid is None:
        print('user not found')
        return

    user = await ctx.storage.get_user(uid)

    print(f'\tuid: {user["user_id"]}')
    print(f'\tuname: {user["username"]}')
    print(f'\tdiscrim: {user["discriminator"]}')

    print('\n you sure you want to delete user? press Y (uppercase)')
    confirm = input()

    if confirm != 'Y':
        print('not confirmed')
        return

    await delete_user(uid)
    print('ok')


def setup(subparser):
    setup_test_parser = subparser.add_parser(
        'adduser',
        help='create a user',
    )

    setup_test_parser.add_argument(
        'username', help='username of the user')
    setup_test_parser.add_argument(
        'email', help='email of the user')
    setup_test_parser.add_argument(
        'password', help='password of the user')

    setup_test_parser.set_defaults(func=adduser)

    staff_parser = subparser.add_parser(
        'make_staff',
        help='make a user staff',
        description=make_staff.__doc__
    )

    staff_parser.add_argument('username')
    staff_parser.add_argument(
        'discrim', help='the discriminator of the user')

    staff_parser.set_defaults(func=make_staff)

    del_user_parser = subparser.add_parser(
        'deluser', help='delete a single user')

    del_user_parser.add_argument('username')
    del_user_parser.add_argument('discriminator')

    del_user_parser.set_defaults(func=del_user)

    token_parser = subparser.add_parser(
        'generate_token',
        help='generate a token for specified bot',
        description=generate_bot_token.__doc__)

    token_parser.add_argument('user_id')

    token_parser.set_defaults(func=generate_bot_token)
