from quart import Blueprint, jsonify

bp = Blueprint('gateway', __name__)


@bp.route('/gateway')
def api_gateway():
    return jsonify({"url": "..."})

# TODO: /gateway/bot (requires token)
