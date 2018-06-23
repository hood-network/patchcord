import base64
import binascii

from itsdangerous import Signer, BadSignature
from logbook import Logger
from quart import request, current_app as app

from .errors import Forbidden, Unauthorized


log = Logger(__name__)


async def raw_token_check(token, db=None):
    db = db or app.db
    user_id, _hmac = token.split('.')

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
        return user_id
    except BadSignature:
        log.warning('token failed for uid {}', user_id)
        raise Forbidden('Invalid token')


async def token_check():
    """Check token information."""
    try:
        token = request.headers['Authorization']
    except KeyError:
        raise Unauthorized('No token provided')

    if token.startswith('Bot '):
        token = token.replace('Bot ', '')

    return await raw_token_check(token)
