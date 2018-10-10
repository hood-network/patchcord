import random
import base64

import asyncpg
import itsdangerous
import bcrypt
from quart import Blueprint, jsonify, request, current_app as app

from litecord.snowflake import get_snowflake
from litecord.errors import BadRequest
from litecord.auth import token_check


bp = Blueprint('auth', __name__)


async def hash_data(data: str) -> str:
    """Hash information with bcrypt."""
    buf = data.encode()

    hashed = await app.loop.run_in_executor(
        None, bcrypt.hashpw, buf, bcrypt.gensalt(14)
    )

    return hashed.decode()


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
    j = await request.get_json()
    email, password, username = j['email'], j['password'], j['username']

    new_id = get_snowflake()
    new_discrim = str(random.randint(1, 9999))
    pwd_hash = await hash_data(password)

    try:
        await app.db.execute("""
        INSERT INTO users (id, email, username,
                        discriminator, password_hash)
        VALUES ($1, $2, $3, $4, $5)
        """, new_id, email, username, new_discrim, pwd_hash)
    except asyncpg.UniqueViolationError:
        raise BadRequest('Email already used.')

    return jsonify({
        'token': make_token(new_id, pwd_hash)
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

    await app.db.execute("""
    UPDATE users
    SET verified = true
    """, user_id)

    return '', 204
