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
from datetime import datetime, date
import itsdangerous
import bcrypt
from quart import Blueprint, jsonify, request, current_app as app
from logbook import Logger


from litecord.auth import token_check
from litecord.common.users import create_user
from litecord.schemas import validate, REGISTER, REGISTER_WITH_INVITE, LOGIN, LOGIN_v6
from litecord.errors import ManualFormError
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
    user_id = base64.b64encode(str(user_id).encode()).rstrip(b"=")

    return signer.sign(user_id).decode()


@bp.route("/register", methods=["POST"])
async def register():
    """Register a single user."""
    enabled = app.config.get("REGISTRATIONS")
    if not enabled:
        error = {"code": "REGISTRATIONS_DISABLED", "message": "Registrations are disabled."}
        raise ManualFormError(email=error, username=error)

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

    date_of_birth = None
    if j.get("date_of_birth"):
        today = date.today()
        date_of_birth = datetime.strptime(j["date_of_birth"], "%Y-%m-%d")
        if (today.year - date_of_birth.year - ((today.month, today.day) < (date_of_birth.month, date_of_birth.day))) < 13:
            raise ManualFormError(date_of_birth={"code": "DATE_OF_BIRTH_UNDERAGE", "message": "You must be at least 13 years old to register."})

    new_id, pwd_hash = await create_user(username, email, password, date_of_birth)

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
        raise ManualFormError(invcode={"code": "INVITATION_CODE_INVALID", "message": "Invalid instance invite."})

    if row["max_uses"] > 0 and row["uses"] >= row["max_uses"]:
        raise ManualFormError(invcode={"code": "INVITATION_CODE_INVALID", "message": "Invalid instance invite."})

    date_of_birth = None
    if data.get("date_of_birth"):
        today = date.today()
        date_of_birth = datetime.strptime(data["date_of_birth"], "%Y-%m-%d")
        if (today.year - date_of_birth.year - ((today.month, today.day) < (date_of_birth.month, date_of_birth.day))) < 13:
            raise ManualFormError(date_of_birth={"code": "DATE_OF_BIRTH_UNDERAGE", "message": "You must be at least 13 years old to register."})

    await app.db.execute(
        """
    UPDATE instance_invites
    SET uses = uses + 1
    WHERE code = $1
    """,
        invcode,
    )

    user_id, pwd_hash = await create_user(
        data["username"], data["email"], data["password"], date_of_birth
    )

    return jsonify({"token": make_token(user_id, pwd_hash)})


@bp.route("/login", methods=["POST"])
async def login():
    j = await request.get_json()
    if "email" in j:
        j = validate(await request.get_json(), LOGIN_v6)
    else:
        j = validate(await request.get_json(), LOGIN)

    try:
        email, password = j["login"], j["password"]
    except KeyError:
        # Old API versions
        email, password = j["email"], j["password"]

    error = {"code": "INVALID_LOGIN", "message": "Login or password is invalid."}

    row = await app.db.fetchrow(
        """
    SELECT id, password_hash
    FROM users
    WHERE email = $1
    """,
        email,
    )

    if not row:
        raise ManualFormError(login=error, email=error, password=error)

    user_id, pwd_hash = row
    if not await check_password(pwd_hash, password):
        raise ManualFormError(login=error, email=error, password=error)

    user_settings = await app.db.fetchrow(
        """
    SELECT locale, theme
    FROM user_settings
    WHERE id = $1
    """,
        user_id,
    )

    return jsonify({"token": make_token(user_id, pwd_hash), "user_id": str(user_id), "user_settings": dict(user_settings)})


@bp.route("/consent-required", methods=["GET"])
async def consent_required():
    return jsonify({"required": True})


@bp.route("/location-metadata", methods=["GET"])
async def location_metadata():
    return jsonify(
        {
            "consent_required": True,
            "country_code": "US",
            "promotional_email_opt_in": {"required": True, "pre_checked": False}
        }
    )


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
