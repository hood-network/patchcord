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
