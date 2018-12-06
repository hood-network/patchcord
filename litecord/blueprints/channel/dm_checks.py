from quart import current_app as app

from litecord.errors import Forbidden
from litecord.enums import RelationshipType


class ForbiddenDM(Forbidden):
    error_code = 50007


async def dm_pre_check(user_id: int, channel_id: int, peer_id: int):
    """Check if the user can DM the peer."""
    # first step is checking if there is a block in any direction
    blockrow = await app.db.fetchrow("""
    SELECT rel_type
    FROM relationships
    WHERE rel_type = $3
      AND user_id IN ($1, $2)
      AND peer_id IN ($1, $2)
    """, user_id, peer_id, RelationshipType.BLOCK.value)

    if blockrow is not None:
        raise ForbiddenDM()

    # now comes the fun part, which is guild settings.
    mutual_guilds = await app.user_storage.get_mutual_guilds(user_id, peer_id)

    # user_settings.restricted_guilds gives us the dms a user doesn't
    # want dms from, so we use that setting from both user and peer

    user_settings = await app.user_storage.get_user_settings(user_id)
    peer_settings = await app.user_storage.get_user_settings(peer_id)

    restricted_user = [int(v) for v in user_settings['restricted_guilds']]
    restricted_peer = [int(v) for v in peer_settings['restricted_guilds']]

    restricted_user = set(restricted_user)
    restricted_peer = set(restricted_peer)

    mutual_guilds -= restricted_user
    mutual_guilds -= restricted_peer

    # if after this filtering we don't have any more guilds, error
    if not mutual_guilds:
        raise ForbiddenDM()
