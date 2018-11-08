import base64
import binascii

from itsdangerous import Signer, BadSignature
from logbook import Logger
from quart import request, current_app as app

from .errors import Forbidden, Unauthorized


log = Logger(__name__)


async def raw_token_check(token, db=None):
    db = db or app.db

    # just try by fragments instead of
    # unpacking
    fragments = token.split('.')
    user_id = fragments[0]

    try:
        user_id = base64.b64decode(user_id.encode())
        user_id = int(user_id)
    except (ValueError, binascii.Error):
        raise Unauthorized('Invalid user ID type')

    pwd_hash = await db.fetchval("""
    SELECT password_hash
    FROM users
    WHERE id = $1
    """, user_id)

    if not pwd_hash:
        raise Unauthorized('User ID not found')

    signer = Signer(pwd_hash)

    try:
        signer.unsign(token)
        log.debug('login for uid {} successful', user_id)

        # update the user's last_session field
        # so that we can keep an exact track of activity,
        # even on long-lived single sessions (that can happen
        # with people leaving their clients open forever)
        await db.execute("""
        UPDATE users
        SET last_session = (now() at time zone 'utc')
        WHERE id = $1
        """, user_id)

        return user_id
    except BadSignature:
        log.warning('token failed for uid {}', user_id)
        raise Forbidden('Invalid token')


async def token_check():
    """Check token information."""
    # first, check if the request info already has a uid
    try:
        return request.user_id
    except AttributeError:
        pass

    try:
        token = request.headers['Authorization']
    except KeyError:
        raise Unauthorized('No token provided')

    if token.startswith('Bot '):
        token = token.replace('Bot ', '')

    user_id = await raw_token_check(token)
    request.user_id = user_id
    return user_id
