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

import pytest


@pytest.mark.asyncio
async def test_science_empty(test_cli):
    """Test that the science route gives nothing."""
    resp = await test_cli.post("/api/v6/science")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_harvest_empty(test_cli):
    """test that the harvest route is empty"""
    resp = await test_cli.get("/api/v6/users/@me/harvest")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_consent_non_consenting(test_cli_user):
    """Test the consent route to see if we're still on
    a non-consent status regarding data collection."""
    resp = await test_cli_user.get("/api/v6/users/@me/consent")
    assert resp.status_code == 200

    rjson = await resp.json
    assert isinstance(rjson, dict)

    # assert that we did not consent to those
    assert not rjson["usage_statistics"]["consented"]
    assert not rjson["personalization"]["consented"]
