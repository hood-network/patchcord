import base64

import itsdangerous
import bcrypt
from quart import Blueprint, jsonify, request, current_app as app

from litecord.auth import token_check, create_user
from litecord.schemas import validate, REGISTER, REGISTER_WITH_INVITE
from litecord.errors import BadRequest


bp = Blueprint('auth', __name__)


async def check_password(pwd_hash: str, given_password: str) -> bool:
    """Check if a given password matches the given hash."""
    pwd_encoded = pwd_hash.encode()
    given_encoded = given_password.encode()

    return await app.loop.run_in_executor(
        None, bcrypt.checkpw, given_encoded, pwd_encoded
    )


def make_token(user_id, user_pwd_hash) -> str:
    """Generate a single token for a user."""
    signer = itsdangerous.Signer(user_pwd_hash)
    user_id = base64.b64encode(str(user_id).encode())

    return signer.sign(user_id).decode()


@bp.route('/register', methods=['POST'])
async def register():
    """Register a single user."""
    enabled = app.config.get('REGISTRATIONS')
    if not enabled:
        return 'Registrations disabled', 405

    j = validate(await request.get_json(), REGISTER)
    email, password, username = j['email'], j['password'], j['username']

    new_id, pwd_hash = await create_user(
        username, email, password, app.db
    )

    return jsonify({
        'token': make_token(new_id, pwd_hash)
    })


@bp.route('/register_inv', methods=['POST'])
async def _register_with_invite():
    data = await request.form
    data = validate(await request.form, REGISTER_WITH_INVITE)

    invcode = data['invcode']

    row = await app.db.fetchrow("""
    SELECT uses, max_uses
    FROM instance_invites
    WHERE code = $1
    """, invcode)

    if row is None:
        raise BadRequest('unknown instance invite')

    if row['max_uses'] != -1 and row['uses'] >= row['max_uses']:
        raise BadRequest('invite expired')

    await app.db.execute("""
    UPDATE instance_invites
    SET uses = uses + 1
    WHERE code = $1
    """, invcode)

    user_id, pwd_hash = await create_user(
        data['username'], data['email'], data['password'], app.db)

    return jsonify({
        'token': make_token(user_id, pwd_hash),
        'user_id': str(user_id),
    })


@bp.route('/login', methods=['POST'])
async def login():
    j = await request.get_json()
    email, password = j['email'], j['password']

    row = await app.db.fetchrow("""
    SELECT id, password_hash
    FROM users
    WHERE email = $1
    """, email)

    if not row:
        return jsonify({'email': ['User not found.']}), 401

    user_id, pwd_hash = row

    if not await check_password(pwd_hash, password):
        return jsonify({'password': ['Password does not match.']}), 401

    return jsonify({
        'token': make_token(user_id, pwd_hash)
    })


@bp.route('/consent-required', methods=['GET'])
async def consent_required():
    return jsonify({
        'required': True,
    })


@bp.route('/verify/resend', methods=['POST'])
async def verify_user():
    user_id = await token_check()

    # TODO: actually verify a user by sending an email
    await app.db.execute("""
    UPDATE users
    SET verified = true
    WHERE id = $1
    """, user_id)

    new_user = await app.storage.get_user(user_id, True)
    await app.dispatcher.dispatch_user(
        user_id, 'USER_UPDATE', new_user)

    return '', 204
