import base64
import logging

from itsdangerous import Signer, BadSignature
from quart import request, current_app as app

from .errors import AuthError


log = logging.getLogger(__name__)


async def token_check():
    """Check token information."""
    try:
        token = request.headers['Authorization']
    except KeyError:
        raise AuthError('No token provided')

    user_id, _hmac = token.split('.')

    user_id = base64.b64decode(user_id.encode('utf-8'))
    try:
        user_id = int(user_id)
    except ValueError:
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
