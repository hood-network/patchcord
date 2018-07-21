from quart import Blueprint, jsonify

bp = Blueprint('science', __name__)


@bp.route('/science', methods=['POST'])
async def science():
    return '', 204


@bp.route('/applications', methods=['GET'])
async def applications():
    return jsonify([])


@bp.route('/experiments', methods=['GET'])
async def experiments():
    return jsonify({
        'assignments': []
    })
