"""

Litecord
Copyright (C) 2018  Luna Mendes

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

from quart import Blueprint, send_file, current_app as app

bp = Blueprint('attachments', __name__)

@bp.route('/attachments'
          '/<int:channel_id>/<int:message_id>/<filename>',
          methods=['GET'])
async def _get_attachment(channel_id: int, message_id: int,
                          filename: str):
    attach_id = await app.db.fetchval("""
    SELECT id
    FROM attachments
    WHERE channel_id = $1
      AND message_id = $2
      AND filename = $3
    """, channel_id, message_id, filename)

    if attach_id is None:
        return '', 404

    ext = filename.split('.')[-1]

    return await send_file(f'./attachments/{attach_id}.{ext}')
