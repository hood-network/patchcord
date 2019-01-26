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

from tests.credentials import CREDS
from litecord.blueprints.auth import create_user
from manage.cmd.users import set_user_staff


async def setup_tests(ctx, _args):
    """Setup users for the testing environment."""
    for name, creds in CREDS.items():
        uid, _ = await create_user(
            creds['username'],
            creds['email'],
            creds['password'],
            ctx.db,
            ctx.loop
        )

        print(f'created {name} user: {uid}')

        if name == 'admin':
            await set_user_staff(uid, ctx)

    print('OK')


def setup(subparser):
    setup_test_parser = subparser.add_parser(
        'setup_tests',
        help='Create test users',
    )

    setup_test_parser.set_defaults(func=setup_tests)
