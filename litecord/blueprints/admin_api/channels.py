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

from quart import Blueprint, jsonify
from typing import TYPE_CHECKING

from litecord.auth import admin_check
from litecord.blueprints.channel.messages import handle_get_messages
from litecord.common.interop import message_view
from litecord.schemas import validate
from litecord.errors import InternalServerError, NotFound
from litecord.utils import extract_limit

if TYPE_CHECKING:
    from litecord.typing_hax import app, request
else:
    from quart import current_app as app, request



bp = Blueprint("channels_admin", __name__)


@bp.route("", methods=["GET"], strict_slashes=False)
async def query_channels():
    await admin_check()

    limit = extract_limit(request, 1, 25, 100)
    j = validate(
        request.args.to_dict(),
        {
            "q": {"coerce": str, "required": False, "maxlength": 32},
            "offset": {"coerce": int, "default": 0},
        },
    )
    query = j.get("q") or ""
    offset = j["offset"]

    # TODO
    raise InternalServerError()


@bp.route("/<int:target_id>", methods=["GET"])
async def get_other(target_id):
    await admin_check()
    other = await app.storage.get_channel(target_id)
    if not other:
        raise NotFound(10003)
    return jsonify(other)


@bp.route("/<int:channel_id>", methods=["DELETE"])
@bp.route("/<int:channel_id>/delete", methods=["POST"])
async def delete_channel(channel_id: int):
    await admin_check()
    # TODO
    raise InternalServerError()


@bp.route("/<int:channel_id>", methods=["PATCH"])
async def edit_channel(channel_id: int):
    await admin_check()
    # TODO
    raise InternalServerError()


@bp.route("/<int:channel_id>/messages", methods=["GET"])
async def get_messages(channel_id):
    await admin_check()
    return jsonify(await handle_get_messages(channel_id))


@bp.route("/<int:channel_id>/messages/<int:message_id>", methods=["GET"])
async def get_single_message(channel_id, message_id):
    await admin_check()

    message = await app.storage.get_message(message_id, user_id)
    if not message:
        raise NotFound(10008)

    return jsonify(message_view(message))
