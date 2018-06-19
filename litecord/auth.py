import base64
import logging
import binascii

from itsdangerous import Signer, BadSignature
from quart import request, current_app as app

from .errors import AuthError


log = logging.getLogger(__name__)


async def raw_token_check(token):
    user_id, _hmac = token.split('.')

    try:
        user_id = base64.b64decode(user_id.encode('utf-8'))
        user_id = int(user_id)
    except (ValueError, binascii.Error):
        raise AuthError('Invalid user ID type')

    pwd_hash = await app.db.fetchval("""
    SELECT password_hash
    FROM users
    WHERE id = $1
    """, user_id)

    if not pwd_hash:
        raise AuthError('User ID not found')

    signer = Signer(pwd_hash)

    try:
        signer.unsign(token)
        log.debug(f'login for uid {user_id} successful')
        return user_id
    except BadSignature:
        log.warning('token fail for uid {user_id}')
        raise AuthError('Invalid token')


async def token_check():
    """Check token information."""
    try:
        token = request.headers['Authorization']
    except KeyError:
        raise AuthError('No token provided')

    await raw_token_check(token)
