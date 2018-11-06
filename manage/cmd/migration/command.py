async def migrate_cmd(app, args):
    """Main migration command.

    This makes sure the database
    is updated.
    """
    print('not implemented yet')


def setup(subparser):
    migrate_parser = subparser.add_parser(
        'migrate',
        help='Run migration tasks',
        description=migrate_cmd.__doc__
    )

    migrate_parser.set_defaults(func=migrate_cmd)
