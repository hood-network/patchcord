import pytest


@pytest.mark.asyncio
async def test_index(test_cli):
    """Test if the main index page works."""
    resp = await test_cli.get('/')
    assert resp.status_code == 200
    assert (await resp.get_data()).decode() == 'hewwo'
