from quart import Blueprint, current_app as app, jsonify, request

bp = Blueprint('nodeinfo', __name__)


@bp.route('/.well-known/nodeinfo')
async def _dummy_nodeinfo_index():
    proto = 'http' if not app.config['IS_SSL'] else 'https'
    return jsonify({
        'links': [{
            'href': f'{proto}://{request.host}/nodeinfo/2.0.json',
            'rel': 'http://nodeinfo.diaspora.software/ns/schema/2.0'
        }]
    })


@bp.route('/nodeinfo/2.0.json')
async def _dummy_nodeinfo():
    usercount = await app.db.fetchval("""
    SELECT COUNT(*)
    FROM users
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
            'localPosts': -1,
            'users': {
                'total': usercount
            }
        },
        'version': '2.0',
    })
