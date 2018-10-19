"""
blueprint for direct messages
"""

from asyncpg import UniqueViolationError
from quart import Blueprint, request, current_app as app, jsonify
from logbook import Logger

from ..schemas import validate, CREATE_DM, CREATE_GROUP_DM
from ..enums import ChannelType
from ..snowflake import get_snowflake

from .auth import token_check

log = Logger(__name__)
bp = Blueprint('dms', __name__)


@bp.route('/@me/channels', methods=['GET'])
async def get_dms():
    """Get the open DMs for the user."""
    user_id = await token_check()
    dms = await app.storage.get_dms(user_id)
    return jsonify(dms)


async def try_dm_state(user_id: int, dm_id: int):
    """Try inserting the user into the dm state
    for the given DM.

    Does not do anything if the user is already
    in the dm state.
    """
    await app.db.execute("""
    INSERT INTO dm_channel_state (user_id, dm_id)
    VALUES ($1, $2)
    ON CONFLICT DO NOTHING
    """, user_id, dm_id)


async def create_dm(user_id, recipient_id):
    """Create a new dm with a user,
    or get the existing DM id if it already exists."""
    dm_id = get_snowflake()

    try:
        await app.db.execute("""
        INSERT INTO channels (id, channel_type)
        VALUES ($1, $2)
        """, dm_id, ChannelType.DM.value)

        await app.db.execute("""
        INSERT INTO dm_channels (id, party1_id, party2_id)
        VALUES ($1, $2, $3)
        """, dm_id, user_id, recipient_id)

        # the dm state is something we use
        # to give the currently "open dms"
        # on the client.

        # we don't open a dm for the peer/recipient
        # until the user sends a message.
        await try_dm_state(user_id, dm_id)

    except UniqueViolationError:
        # the dm already exists
        dm_id = await app.db.fetchval("""
        SELECT id
        FROM dm_channels
        WHERE (party1_id = $1 OR party2_id = $1) AND
              (party2_id = $2 OR party2_id = $2)
        """, user_id, recipient_id)

    dm = await app.storage.get_dm(dm_id, user_id)
    return jsonify(dm)


@bp.route('/@me/channels', methods=['POST'])
async def start_dm():
    """Create a DM with a user."""
    user_id = await token_check()
    j = validate(await request.get_json(), CREATE_DM)
    recipient_id = j['recipient_id']

    return await create_dm(user_id, recipient_id)


@bp.route('/<int:p_user_id>/channels', methods=['POST'])
async def create_group_dm(p_user_id: int):
    """Create a DM or a Group DM with user(s)."""
    user_id = await token_check()
    assert user_id == p_user_id

    j = validate(await request.get_json(), CREATE_GROUP_DM)
    recipients = j['recipients']

    if len(recipients) == 1:
        # its a group dm with 1 user... a dm!
        return await create_dm(user_id, int(recipients[0]))

    # TODO: group dms
    return 'group dms not implemented', 500
