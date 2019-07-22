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

def email() -> str:
    return f'{secrets.token_hex(5)}@{secrets.token_hex(5)}.com'


class TestClient:
    """Test client that wraps pytest-sanic's TestClient and a test
    user and adds authorization headers to test requests."""
    def __init__(self, test_cli, test_user):
        self.cli = test_cli
        self.app = test_cli.app
        self.user = test_user

    def __getitem__(self, key):
        return self.user[key]

    def _inject_auth(self, kwargs: dict) -> list:
        """Inject the test user's API key into the test request before
        passing the request on to the underlying TestClient."""
        headers = kwargs.get('headers', {})
        headers['authorization'] = self.user['token']
        return headers

    async def get(self, *args, **kwargs):
        """Send a GET request."""
        kwargs['headers'] = self._inject_auth(kwargs)
        return await self.cli.get(*args, **kwargs)

    async def post(self, *args, **kwargs):
        """Send a POST request."""
        kwargs['headers'] = self._inject_auth(kwargs)
        return await self.cli.post(*args, **kwargs)

    async def put(self, *args, **kwargs):
        """Send a POST request."""
        kwargs['headers'] = self._inject_auth(kwargs)
        return await self.cli.put(*args, **kwargs)

    async def patch(self, *args, **kwargs):
        """Send a PATCH request."""
        kwargs['headers'] = self._inject_auth(kwargs)
        return await self.cli.patch(*args, **kwargs)

    async def delete(self, *args, **kwargs):
        """Send a DELETE request."""
        kwargs['headers'] = self._inject_auth(kwargs)
        return await self.cli.delete(*args, **kwargs)
