import pytest

from tests.common import login


@pytest.mark.asyncio
async def test_science_empty(test_cli):
    """Test that the science route gives nothing."""
    resp = await test_cli.post('/api/v6/science')
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_harvest_empty(test_cli):
    """test that the harvest route is empty"""
    resp = await test_cli.get('/api/v6/users/@me/harvest')
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_consent_non_consenting(test_cli):
    """Test the consent route to see if we're still on
    a non-consent status regarding data collection."""
    token = await login('normal', test_cli)

    resp = await test_cli.get('/api/v6/users/@me/consent', headers={
        'Authorization': token
    })

    assert resp.status_code == 200

    rjson = await resp.json
    assert isinstance(rjson, dict)

    # assert that we did not consent to those
    assert not rjson['usage_statistics']['consented']
    assert not rjson['personalization']['consented']
