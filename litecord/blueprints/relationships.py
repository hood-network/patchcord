from quart import Blueprint, jsonify, request, current_app as app
from asyncpg import UniqueViolationError

from ..auth import token_check
from ..schemas import validate, RELATIONSHIP, SPECIFIC_FRIEND
from ..enums import RelationshipType


bp = Blueprint('relationship', __name__)


@bp.route('/@me/relationships', methods=['GET'])
async def get_me_relationships():
    user_id = await token_check()
    return jsonify(
        await app.user_storage.get_relationships(user_id))


async def _unsub_friend(user_id, peer_id):
    await app.dispatcher.unsub('friend', user_id, peer_id)
    await app.dispatcher.unsub('friend', peer_id, user_id)


async def _sub_friend(user_id, peer_id):
    await app.dispatcher.sub('friend', user_id, peer_id)
    await app.dispatcher.sub('friend', peer_id, user_id)


async def make_friend(user_id: int, peer_id: int,
                      rel_type=RelationshipType.FRIEND.value):
    _friend = RelationshipType.FRIEND.value
    _block = RelationshipType.BLOCK.value

    try:
        await app.db.execute("""
        INSERT INTO relationships (user_id, peer_id, rel_type)
        VALUES ($1, $2, $3)
        """, user_id, peer_id, rel_type)
    except UniqueViolationError:
        # try to update rel_type
        old_rel_type = await app.db.fetchval("""
        SELECT rel_type
        FROM relationships
        WHERE user_id = $1 AND peer_id = $2
        """, user_id, peer_id)

        if old_rel_type == _friend and rel_type == _block:
            await app.db.execute("""
            UPDATE relationships
            SET rel_type = $1
            WHERE user_id = $2 AND peer_id = $3
            """, rel_type, user_id, peer_id)

            # remove any existing friendship before the block
            await app.db.execute("""
            DELETE FROM relationships
            WHERE peer_id = $1 AND user_id = $2 AND rel_type = $3
            """, peer_id, user_id, _friend)

            await app.dispatcher.dispatch_user(
                peer_id, 'RELATIONSHIP_REMOVE', {
                    'type': _friend,
                    'id': str(user_id)
                }
            )

            await _unsub_friend(user_id, peer_id)

            # returning none will make sure
            # to dispatch a RELATIONSHIP_ADD to the user
            return

    # check if this is an acceptance
    # of a friend request
    existing = await app.db.fetchrow("""
    SELECT user_id, peer_id
    FROM relationships
    WHERE user_id = $1 AND peer_id = $2 AND rel_type = $3
    """, peer_id, user_id, _friend)

    _dispatch = app.dispatcher.dispatch_user

    if existing:
        # accepted a friend request, dispatch respective
        # relationship events
        await _dispatch(user_id, 'RELATIONSHIP_REMOVE', {
            'type': RelationshipType.INCOMING.value,
            'id': str(peer_id)
        })

        await _dispatch(user_id, 'RELATIONSHIP_ADD', {
            'type': _friend,
            'id': str(peer_id),
            'user': await app.storage.get_user(peer_id)
        })

        await _dispatch(peer_id, 'RELATIONSHIP_ADD', {
            'type': _friend,
            'id': str(user_id),
            'user': await app.storage.get_user(user_id)
        })

        await _sub_friend(user_id, peer_id)

        return '', 204

    # check if friend AND not acceptance of fr
    if rel_type == _friend:
        await _dispatch(user_id, 'RELATIONSHIP_ADD', {
            'id': str(peer_id),
            'type': RelationshipType.OUTGOING.value,
            'user': await app.storage.get_user(peer_id),
        })

        await _dispatch(peer_id, 'RELATIONSHIP_ADD', {
            'id': str(user_id),
            'type': RelationshipType.INCOMING.value,
            'user': await app.storage.get_user(user_id)
        })

        # we don't make the pubsub link
        # until the peer accepts the friend request

        return '', 204

    return


class RelationshipFailed(BadRequest):
    error_code = 80004


@bp.route('/@me/relationships', methods=['POST'])
async def post_relationship():
    user_id = await token_check()
    j = validate(await request.get_json(), SPECIFIC_FRIEND)

    uid = await app.storage.search_user(j['username'],
                                        str(j['discriminator']))

    if not uid:
        raise RelationshipFailed()

    res = await make_friend(user_id, uid)

    # NOTE: don't know what status code should I send
    if res is None:
        return '', 500

    return '', 204


@bp.route('/@me/relationships/<int:peer_id>', methods=['PUT'])
async def add_relationship(peer_id: int):
    """Add a relationship to the peer."""
    user_id = await token_check()
    payload = validate(await request.get_json(), RELATIONSHIP)
    rel_type = payload['type']

    res = await make_friend(user_id, peer_id, rel_type)

    if res is not None:
        return res

    # make_friend did not succeed, so we
    # assume it is a block and dispatch
    # the respective RELATIONSHIP_ADD.
    await app.dispatcher.dispatch_user(user_id, 'RELATIONSHIP_ADD', {
        'id': str(peer_id),
        'type': RelationshipType.BLOCK.value,
        'user': await app.storage.get_user(peer_id)
    })

    await _unsub_friend(user_id, peer_id)

    return '', 204


@bp.route('/@me/relationships/<int:peer_id>', methods=['DELETE'])
async def remove_relationship(peer_id: int):
    """Remove an existing relationship"""
    user_id = await token_check()
    _friend = RelationshipType.FRIEND.value
    _block = RelationshipType.BLOCK.value
    _dispatch = app.dispatcher.dispatch_user

    rel_type = await app.db.fetchval("""
    SELECT rel_type
    FROM relationships
    WHERE user_id = $1 AND peer_id = $2
    """, user_id, peer_id)

    incoming_rel_type = await app.db.fetchval("""
    SELECT rel_type
    FROM relationships
    WHERE user_id = $1 AND peer_id = $2
    """, peer_id, user_id)

    # if any of those are friend
    if _friend in (rel_type, incoming_rel_type):
        # closing the friendship, have to delete both rows
        await app.db.execute("""
        DELETE FROM relationships
        WHERE (
            (user_id = $1 AND peer_id = $2) OR
            (user_id = $2 AND peer_id = $1)
            ) AND rel_type = $3
        """, user_id, peer_id, _friend)

        # if there wasnt any mutual friendship before,
        # assume they were requests of INCOMING
        # and OUTGOING.
        user_del_type = RelationshipType.OUTGOING.value if \
            incoming_rel_type != _friend else _friend

        await _dispatch(user_id, 'RELATIONSHIP_REMOVE', {
            'id': str(peer_id),
            'type': user_del_type,
        })

        peer_del_type = RelationshipType.INCOMING.value if \
            incoming_rel_type != _friend else _friend

        await _dispatch(peer_id, 'RELATIONSHIP_REMOVE', {
            'id': str(user_id),
            'type': peer_del_type,
        })

        await _unsub_friend(user_id, peer_id)

        return '', 204

    # was a block!
    await app.db.execute("""
    DELETE FROM relationships
    WHERE user_id = $1 AND peer_id = $2 AND rel_type = $3
    """, user_id, peer_id, _block)

    await _dispatch(user_id, 'RELATIONSHIP_REMOVE', {
        'id': str(peer_id),
        'type': _block,
    })

    await _unsub_friend(user_id, peer_id)

    return '', 204


@bp.route('/<int:peer_id>/relationships', methods=['GET'])
async def get_mutual_friends(peer_id: int):
    """Fetch a users' mutual friends with the current user."""
    user_id = await token_check()
    _friend = RelationshipType.FRIEND.value

    peer = await app.storage.get_user(peer_id)

    if not peer:
        return '', 204

    # NOTE: maybe this could be better with pure SQL calculations
    # but it would be beyond my current SQL knowledge, so...
    user_rels = await app.user_storage.get_relationships(user_id)
    peer_rels = await app.user_storage.get_relationships(peer_id)

    user_friends = {rel['user']['id']
                    for rel in user_rels if rel['type'] == _friend}
    peer_friends = {rel['user']['id']
                    for rel in peer_rels if rel['type'] == _friend}

    # get the intersection, then map them to Storage.get_user() calls
    mutual_ids = user_friends & peer_friends

    mutual_friends = []

    for friend_id in mutual_ids:
        mutual_friends.append(
            await app.storage.get_user(int(friend_id))
        )

    return jsonify(mutual_friends)
