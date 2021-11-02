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

import secrets
import sys
import os

import pytest

# this is very hacky.
sys.path.append(os.getcwd())

from tests.common import email, TestClient

from run import app as main_app

from litecord.common.users import create_user, delete_user
from litecord.enums import UserFlags
from litecord.blueprints.auth import make_token


@pytest.fixture(name="app")
async def _test_app(unused_tcp_port):
    main_app.config["_testing"] = True

    # reassign an unused tcp port for websockets
    # since the config might give a used one.
    ws_port = unused_tcp_port

    main_app.config["IS_SSL"] = False
    main_app.config["WS_PORT"] = ws_port
    main_app.config["WEBSOCKET_URL"] = f"localhost:{ws_port}"

    # testing user creations requires hardcoding this to true
    # on testing
    main_app.config["REGISTRATIONS"] = True

    # make sure we're calling the before_serving hooks
    await main_app.startup()

    # https://docs.pytest.org/en/latest/fixture.html#fixture-finalization-executing-teardown-code
    yield main_app

    # properly teardown
    await main_app.shutdown()


@pytest.fixture(name="test_cli")
def _test_cli(app):
    """Give a test client."""
    return app.test_client()


# code shamelessly stolen from my elixire mr
# https://gitlab.com/elixire/elixire/merge_requests/52
async def _user_fixture_setup(app):
    username = secrets.token_hex(6)
    password = secrets.token_hex(6)
    user_email = email()

    async with app.app_context():
        user_id, pwd_hash = await create_user(username, user_email, password)

    # generate a token for api access
    user_token = make_token(user_id, pwd_hash)

    return {
        "id": user_id,
        "token": user_token,
        "email": user_email,
        "username": username,
        "password": password,
    }


async def _user_fixture_teardown(app, udata: dict):
    async with app.app_context():
        await delete_user(udata["id"])


@pytest.fixture(name="test_user")
async def test_user_fixture(app):
    """Yield a randomly generated test user."""
    udata = await _user_fixture_setup(app)
    yield udata
    await _user_fixture_teardown(app, udata)


@pytest.fixture
async def test_cli_user(test_cli, test_user):
    """Yield a TestClient instance that contains a randomly generated
    user."""
    client = TestClient(test_cli, test_user)
    yield client
    await client.cleanup()


@pytest.fixture
async def test_cli_staff(test_cli):
    """Yield a TestClient with a staff user."""
    # This does not use the test_user because if a given test uses both
    # test_cli_user and test_cli_admin, test_cli_admin will just point to that
    # same test_cli_user, which isn't acceptable.
    app = test_cli.app
    test_user = await _user_fixture_setup(app)
    user_id = test_user["id"]

    # copied from manage.cmd.users.set_user_staff.
    old_flags = await app.db.fetchval(
        """
        SELECT flags FROM users WHERE id = $1
        """,
        user_id,
    )

    new_flags = old_flags | UserFlags.staff

    await app.db.execute(
        """
        UPDATE users SET flags = $1 WHERE id = $2
        """,
        new_flags,
        user_id,
    )

    client = TestClient(test_cli, test_user)
    yield client
    await client.cleanup()
    await _user_fixture_teardown(test_cli.app, test_user)


@pytest.fixture
async def test_cli_bot(test_cli):
    """Yield a TestClient with a bot user."""
    # do not create a new test user to prevent race conditions caused
    # by a test wanting both fixtures
    app = test_cli.app
    test_user = await _user_fixture_setup(app)
    user_id = test_user["id"]

    assert await app.db.fetchval(
        """
        UPDATE users SET bot = true WHERE id = $1 RETURNING bot
        """,
        user_id,
    )

    client = TestClient(test_cli, test_user)
    yield client
    await client.cleanup()
    await _user_fixture_teardown(test_cli.app, test_user)
