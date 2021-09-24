"""

Litecord
Copyright (C) 2018-2021  Luna Mendes and Litecord Contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""

import base64
import secrets

import itsdangerous
import bcrypt
from quart import Blueprint, jsonify, request, current_app as app
from logbook import Logger


from litecord.auth import token_check
from litecord.common.users import create_user
from litecord.schemas import validate, REGISTER, REGISTER_WITH_INVITE
from litecord.errors import BadRequest
from litecord.pubsub.user import dispatch_user
from .invites import use_invite

log = Logger(__name__)
bp = Blueprint("auth", __name__)


async def check_password(pwd_hash: str, given_password: str) -> bool:
    """Check if a given password matches the given hash."""
    pwd_encoded = pwd_hash.encode()
    given_encoded = given_password.encode()

    return await app.loop.run_in_executor(
        None, bcrypt.checkpw, given_encoded, pwd_encoded
    )


def make_token(user_id, user_pwd_hash) -> str:
    """Generate a single token for a user."""
    signer = itsdangerous.TimestampSigner(user_pwd_hash)
    user_id = base64.b64encode(str(user_id).encode())

    return signer.sign(user_id).decode()


@bp.route("/register", methods=["POST"])
async def register():
    """Register a single user."""
    enabled = app.config.get("REGISTRATIONS")
    if not enabled:
        raise BadRequest(
            "Registrations disabled", {"email": "Registrations are disabled."}
        )

    j = await request.get_json()

    if "password" not in j:
        # we need a password to generate a token.
        # passwords are optional, so
        j["password"] = "default_password"

    j = validate(j, REGISTER)

    # they're optional
    email = j.get("email")
    invite = j.get("invite")

    username, password = j["username"], j["password"]

    new_id, pwd_hash = await create_user(username, email, password)

    if invite:
        try:
            await use_invite(new_id, invite)
        except Exception:
            log.exception("failed to use invite for register {} {!r}", new_id, invite)

    return jsonify({"token": make_token(new_id, pwd_hash)})


@bp.route("/register_inv", methods=["POST"])
async def _register_with_invite():
    data = await request.form
    data = validate(await request.form, REGISTER_WITH_INVITE)

    invcode = data["invcode"]

    row = await app.db.fetchrow(
        """
    SELECT uses, max_uses
    FROM instance_invites
    WHERE code = $1
    """,
        invcode,
    )

    if row is None:
        raise BadRequest("unknown instance invite")

    if row["max_uses"] != -1 and row["uses"] >= row["max_uses"]:
        raise BadRequest("invite expired")

    await app.db.execute(
        """
    UPDATE instance_invites
    SET uses = uses + 1
    WHERE code = $1
    """,
        invcode,
    )

    user_id, pwd_hash = await create_user(
        data["username"], data["email"], data["password"]
    )

    return jsonify({"token": make_token(user_id, pwd_hash), "user_id": str(user_id)})


@bp.route("/login", methods=["POST"])
async def login():
    j = await request.get_json()
    try:
        email, password = j["email"], j["password"]
    except KeyError:
        # hack for api v9
        email, password = j["login"], j["password"]

    row = await app.db.fetchrow(
        """
    SELECT id, password_hash
    FROM users
    WHERE email = $1
    """,
        email,
    )

    if not row:
        return jsonify({"email": ["User not found."]}), 401

    user_id, pwd_hash = row

    if not await check_password(pwd_hash, password):
        return jsonify({"password": ["Password does not match."]}), 401

    return jsonify({"token": make_token(user_id, pwd_hash)})


@bp.route("/consent-required", methods=["GET"])
async def consent_required():
    return jsonify({"required": True})


@bp.route("/verify/resend", methods=["POST"])
async def verify_user():
    user_id = await token_check()

    # TODO: actually verify a user by sending an email
    await app.db.execute(
        """
    UPDATE users
    SET verified = true
    WHERE id = $1
    """,
        user_id,
    )

    new_user = await app.storage.get_user(user_id, True)
    await dispatch_user(user_id, ("USER_UPDATE", new_user))

    return "", 204


@bp.route("/logout", methods=["POST"])
async def _logout():
    """Called by the client to logout."""
    return "", 204


@bp.route("/fingerprint", methods=["POST"])
async def _fingerprint():
    """No idea what this route is about."""
    fingerprint_id = app.winter_factory.snowflake()
    fingerprint = f"{fingerprint_id}.{secrets.token_urlsafe(32)}"

    return jsonify({"fingerprint": fingerprint})
