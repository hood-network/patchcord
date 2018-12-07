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

from quart import Blueprint, current_app as app, jsonify, request

bp = Blueprint('nodeinfo', __name__)


@bp.route('/.well-known/nodeinfo')
async def _dummy_nodeinfo_index():
    proto = 'http' if not app.config['IS_SSL'] else 'https'
    main_url = app.config.get('MAIN_URL', request.host)

    return jsonify({
        'links': [{
            'href': f'{proto}://{main_url}/nodeinfo/2.0.json',
            'rel': 'http://nodeinfo.diaspora.software/ns/schema/2.0'
        }]
    })


@bp.route('/nodeinfo/2.0.json')
async def _dummy_nodeinfo():
    usercount = await app.db.fetchval("""
    SELECT COUNT(*)
    FROM users
    """)

    message_count = await app.db.fetchval("""
    SELECT COUNT(*)
    FROM messages
    """)

    return jsonify({
        'metadata': {
            'features': [
                'discord_api'
            ],

            'nodeDescription': 'A Litecord instance',
            'nodeName': 'Litecord/Nya',
            'private': False,

            'federation': {}
        },
        'openRegistrations': app.config['REGISTRATIONS'],
        'protocols': [],
        'software': {
            'name': 'litecord',
            'version': 'litecord v0',
        },

        'services': {
            'inbound': [],
            'outbound': [],
        },

        'usage': {
            'localPosts': message_count,
            'users': {
                'total': usercount
            }
        },
        'version': '2.0',
    })
