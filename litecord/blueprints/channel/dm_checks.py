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

    # TODO: check mutual guilds and guild settings for
    # each user
