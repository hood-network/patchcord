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

import secrets
from typing import Optional
from dataclasses import dataclass

from litecord.common.users import create_user, delete_user
from litecord.blueprints.auth import make_token


def email() -> str:
    return f"{secrets.token_hex(5)}@{secrets.token_hex(5)}.com"


@dataclass
class WrappedUser:
    test_cli: "TestClient"
    id: int
    name: str
    email: str
    password: str
    token: str

    async def refetch(self):
        async with self.test_cli.app.app_context():
            return await self.test_cli.app.storage.get_user(self.id)

    async def delete(self):
        async with self.test_cli.app.app_context():
            return await delete_user(self.id)


class TestClient:
    """Test client wrapper class. Adds Authorization headers to all requests
    and manages test resource setup and destruction."""

    def __init__(self, test_cli, test_user):
        self.cli = test_cli
        self.app = test_cli.app
        self.user = test_user
        self.resources = []

    def __getitem__(self, key):
        return self.user[key]

    def add_resource(self, resource):
        self.resources.append(resource)
        return resource

    async def cleanup(self):
        for resource in self.resources:
            await resource.delete()

    async def create_user(
        self,
        *,
        username: str,
        email: str,
        password: Optional[str] = None,
    ) -> WrappedUser:
        password = password or secrets.token_hex(6)

        async with self.app.app_context():
            user_id, password_hash = await create_user(username, email, password)
            user_token = make_token(user_id, password_hash)

        return self.add_resource(
            WrappedUser(self, user_id, username, email, password, user_token)
        )

    def _inject_auth(self, kwargs: dict) -> list:
        """Inject the test user's API key into the test request before
        passing the request on to the underlying TestClient."""
        headers = kwargs.get("headers", {})
        headers["authorization"] = self.user["token"]
        return headers

    async def get(self, *args, **kwargs):
        """Send a GET request."""
        kwargs["headers"] = self._inject_auth(kwargs)
        return await self.cli.get(*args, **kwargs)

    async def post(self, *args, **kwargs):
        """Send a POST request."""
        kwargs["headers"] = self._inject_auth(kwargs)
        return await self.cli.post(*args, **kwargs)

    async def put(self, *args, **kwargs):
        """Send a POST request."""
        kwargs["headers"] = self._inject_auth(kwargs)
        return await self.cli.put(*args, **kwargs)

    async def patch(self, *args, **kwargs):
        """Send a PATCH request."""
        kwargs["headers"] = self._inject_auth(kwargs)
        return await self.cli.patch(*args, **kwargs)

    async def delete(self, *args, **kwargs):
        """Send a DELETE request."""
        kwargs["headers"] = self._inject_auth(kwargs)
        return await self.cli.delete(*args, **kwargs)
