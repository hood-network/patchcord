import hashlib
import os

from quart import Blueprint, request, current_app as app, jsonify
from logbook import Logger

from ..auth import token_check
from ..schemas import validate, INVITE
from ..enums import ChannelType
from ..errors import BadRequest, Forbidden
from .channels import channel_check
from .guilds import guild_check
from ..utils import async_map

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

    invite_code = hashlib.md5(os.urandom(64)).hexdigest()[:6]

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


@bp.route('/invite/<invite_code>', methods=['GET'])
async def get_invite_2(invite_code: str):
    return await get_invite(invite_code)


@bp.route('/invites/<invite_code>', methods=['DELETE'])
async def delete_invite(invite_code: str):
    user_id = await token_check()

    gid = await app.db.fetchval("""
    SELECT guild_id
    FROM invites
    WHERE code = $1
    """, invite_code)

    if gid is None:
        raise BadRequest('Unknown invite')

    # TODO: check MANAGE_CHANNELS permission
    # for now we'll go with checking owner

    owner_id = await app.db.fetchval("""
    SELECT owner_id
    FROM guilds
    WHERE id = $1
    """. gid)

    if owner_id != user_id:
        raise Forbidden('Not guild owner')

    inv = await app.storage.get_invite(invite_code)

    await app.db.fetchval("""
    DELETE FROM invites
    WHERE code = $1
    """, invite_code)

    return jsonify(inv)


async def _get_inv(code):
    inv = await app.storage.get_invite(code)
    meta = await app.storage.get_invite_metadata(code)
    return {**inv, **meta}


@bp.route('/guilds/<int:guild_id>/invites', methods=['GET'])
async def get_guild_invites(guild_id: int):
    user_id = await token_check()
    await guild_check(user_id, guild_id)

    inv_codes = await app.db.fetch("""
    SELECT code
    FROM invites
    WHERE guild_id = $1
    """, guild_id)

    # TODO: MANAGE_GUILD permission

    inv_codes = [r['code'] for r in inv_codes]
    invs = await async_map(_get_inv, inv_codes)
    return jsonify(invs)


@bp.route('/channels/<int:channel_id>/invites', methods=['GET'])
async def get_channel_invites(channel_id: int):
    user_id = await token_check()
    guild_id = await channel_check(user_id, channel_id)

    inv_codes = await app.db.fetch("""
    SELECT code
    FROM invites
    WHERE guild_id = $1 AND channel_id = $2
    """, guild_id, channel_id)

    # TODO: check MANAGE_CHANNELS permission

    inv_codes = [r['code'] for r in inv_codes]
    invs = await async_map(_get_inv, inv_codes)
    return jsonify(invs)


@bp.route('/invite/<invite_code>', methods=['POST'])
async def use_invite(invite_code):
    user_id = await token_check()

    guild_id = await app.db.fetchval("""
    SELECT guild_id
    FROM invites
    WHERE code = $1
    """, invite_code)

    if not guild_id:
        raise BadRequest('Guild not Found')

    joined = await app.db.fetchval("""
    SELECT joined_at
    FROM members
    WHERE user_id = $1 AND guild_id = $2
    """, user_id, guild_id)

    if joined is not None:
        raise BadRequest('You are already in the guild')

    await app.db.execute("""
    INSERT INTO members (user_id, guild_id)
    VALUES ($1, $2)
    """, user_id, guild_id)

    # add the @everyone role to the invited member
    await app.db.execute("""
    INSERT INTO member_roles (user_id, guild_id, role_id)
    VALUES ($1, $2, $3)
    """, user_id, guild_id, guild_id)

    # tell current members a new member came up
    member = await app.storage.get_member_data_one(guild_id, user_id)
    await app.dispatcher.dispatch_guild(guild_id, 'GUILD_MEMBER_ADD', {
        **member,
        **{
            'guild_id': str(guild_id),
        },
    })

    # subscribe new member to guild, so they get events n stuff
    app.dispatcher.sub_guild(guild_id, user_id)

    # tell the new member that theres the guild it just joined.
    # we use dispatch_user_guild so that we send the GUILD_CREATE
    # just to the shards that are actually tied to it.
    guild = await app.storage.get_guild_full(guild_id, user_id, 250)
    await app.dispatcher.dispatch_user_guild(
        user_id, guild_id, 'GUILD_CREATE', guild)

    # the reply is an invite object for some reason.
    inv = await app.storage.get_invite(invite_code)
    inv_meta = await app.storage.get_invite_metadata(invite_code)

    return jsonify({
        **inv,
        **{
            'inviter': inv_meta['inviter']
        }
    })
