from quart import Blueprint, jsonify

bp = Blueprint('voice', __name__)


@bp.route('/regions', methods=['GET'])
async def voice_regions():
    return jsonify([
        {'name': 'Brazil', 'deprecated': False, 'id': 'Brazil', 'optimal': True, 'vip': True}
    ])
