from quart import Blueprint, jsonify, current_app as app

from ..auth import token_check

bp = Blueprint('gateway', __name__)


def get_gw():
    proto = 'wss://' if app.config['IS_SSL'] else 'ws://'
    return f'{proto}{app.config["WEBSERVER_URL"]}/ws'


@bp.route('/gateway')
def api_gateway():
    return jsonify({
        'url': get_gw()
    })


@bp.route('/gateway/bot')
async def api_gateway_bot():
    user_id = await token_check()

    guild_count = await app.db.fetchval("""
    SELECT COUNT(*)
    FROM members
    WHERE user_id = $1
    """, user_id)

    shards = max(int(guild_count / 1200), 1)

    return jsonify({
        'url': get_gw(),
        'shards': shards,
    })
