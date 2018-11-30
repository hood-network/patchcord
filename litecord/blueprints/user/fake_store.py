"""
fake routes for discord store
"""
from quart import Blueprint, jsonify

bp = Blueprint('fake_store', __name__)


@bp.route('/promotions')
async def _get_promotions():
    return jsonify([])


@bp.route('/users/@me/library')
async def _get_library():
    return jsonify([])


@bp.route('/users/@me/feed/settings')
async def _get_feed_settings():
    return jsonify({
        'subscribed_games': [],
        'subscribed_users': [],
        'unsubscribed_users': [],
        'unsubscribed_games': [],
    })
