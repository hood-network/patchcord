import hashlib
import os

from quart import Blueprint, request, current_app as app, jsonify
from logbook import Logger

from ..auth import token_check
from ..schemas import validate, INVITE
from ..enums import ChannelType
from ..errors import BadRequest
from .channels import channel_check

log = Logger(__name__)
bp = Blueprint('invites', __name__)


@bp.route('/channels/<int:channel_id>/invites', methods=['POST'])
async def create_invite(channel_id):
    user_id = await token_check()

    j = validate(await request.get_json(), INVITE)
    guild_id = await channel_check(user_id, channel_id)

    # TODO: check CREATE_INSTANT_INVITE permission

    chantype = await app.storage.get_chan_type(channel_id)
    if chantype not in (ChannelType.GUILD_TEXT.value,
                        ChannelType.GUILD_VOICE.value):
        raise BadRequest('Invalid channel type')

    invite_code = hashlib.md5(os.urandom(64)).hexdigest()[:16]

    await app.db.execute(
        """
        INSERT INTO invites
            (code, guild_id, channel_id, inviter, max_uses,
            max_age, temporary)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        invite_code, guild_id, channel_id, user_id,
        j['max_uses'], j['max_age'], j['temporary']
    )

    invite = await app.storage.get_invite(invite_code)
    return jsonify(invite)


@bp.route('/invites/<invite_code>', methods=['GET'])
async def get_invite(invite_code: str):
    inv = await app.storage.get_invite(invite_code)

    if request.args.get('with_counts'):
        extra = await app.storage.get_invite_extra(invite_code)
        inv.update(extra)

    return jsonify(inv)
