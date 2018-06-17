import random
import base64

import asyncpg
import itsdangerous
import bcrypt
from quart import Blueprint, jsonify, request, current_app as app

from ..snowflake import get_snowflake
from ..errors import AuthError


bp = Blueprint('auth', __name__)


async def hash_data(data: str) -> str:
    """Hash information with bcrypt."""
    data = bytes(data, 'utf-8')

    future = app.loop.run_in_executor(
        None, bcrypt.hashpw, data, bcrypt.gensalt(14))

    hashed = await future
    return hashed.decode('utf-8')


async def check_password(pwd_hash, given_password) -> bool:
    """Check if a given password matches the given hash."""
    pwd_hash = pwd_hash.encode('utf-8')
    given_password = given_password.encode('utf-8')

    future = app.loop.run_in_executor(
        None, bcrypt.checkpw, pwd_hash, given_password)

    return await future


def make_token(user_id, user_pwd_hash) -> str:
    """Generate a single token for a user."""
    signer = itsdangerous.Signer(user_pwd_hash)
    user_id = base64.b64encode(str(user_id).encode('utf-8'))

    return signer.sign(user_id).decode('utf-8')


@bp.route('/register', methods=['POST'])
async def register():
    """Register a user on litecord"""
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
        raise AuthError('Email already used.')

    return jsonify({
        'token': make_token(new_id, pwd_hash)
    })


@bp.route('/login', methods=['POST'])
async def login():
    """Login one user into Litecord."""
    j = await request.get_json()
    email, password = j['email'], j['password']

    row = await app.db.fetchrow("""
    SELECT id, password_hash
    FROM users
    WHERE email = $1
    """, email)

    if not row:
        return jsonify({'email': ['User not found.']})

    user_id, pwd_hash = row

    if not await check_password(pwd_hash, password):
        return jsonify({'password': ['Password does not match.']})

    return jsonify({
        'token': make_token(user_id, pwd_hash)
    })
