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

import datetime
import string
from random import choice

ALPHABET = string.ascii_lowercase + string.ascii_uppercase + string.digits


async def _gen_inv() -> str:
    """Generate an invite code"""
    return "".join(choice(ALPHABET) for _ in range(6))


async def gen_inv(ctx) -> str:
    """Generate an invite."""
    for _ in range(10):
        possible_inv = await _gen_inv()

        created_at = await ctx.db.fetchval(
            """
        SELECT created_at
        FROM instance_invites
        WHERE code = $1
        """,
            possible_inv,
        )

        if created_at is None:
            return possible_inv

    return None


async def make_inv(ctx, args):
    code = await gen_inv(ctx)

    max_uses = args.max_uses

    await ctx.db.execute(
        """
    INSERT INTO instance_invites (code, max_uses)
    VALUES ($1, $2)
    """,
        code,
        max_uses,
    )

    print(f"invite created with {max_uses} max uses", code)


async def list_invs(ctx, args):
    rows = await ctx.db.fetch(
        """
    SELECT code, created_at, uses, max_uses
    FROM instance_invites
    """
    )

    print(len(rows), "invites")

    for row in rows:
        max_uses = row["max_uses"]
        delta = datetime.datetime.utcnow() - row["created_at"]
        usage = "infinite uses" if max_uses == -1 else f'{row["uses"]} / {max_uses}'

        print(f'\t{row["code"]}, {usage}, made {delta} ago')


async def delete_inv(ctx, args):
    inv = args.invite_code

    res = await ctx.db.execute(
        """
    DELETE FROM instance_invites
    WHERE code = $1
    """,
        inv,
    )

    if res == "DELETE 0":
        print("NOT FOUND")
        return

    print("OK")


def setup(subparser):
    makeinv_parser = subparser.add_parser("makeinv", help="create an invite")

    makeinv_parser.add_argument(
        "max_uses",
        nargs="?",
        type=int,
        default=-1,
        help="Maximum amount of uses before the invite is unavailable",
    )

    makeinv_parser.set_defaults(func=make_inv)

    listinv_parser = subparser.add_parser("listinv", help="list all invites")
    listinv_parser.set_defaults(func=list_invs)

    delinv_parser = subparser.add_parser("delinv", help="delete an invite")
    delinv_parser.add_argument("invite_code")
    delinv_parser.set_defaults(func=delete_inv)
