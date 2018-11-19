from quart import Blueprint, current_app as app
from pathlib import Path

bp = Blueprint('static', __name__)


@bp.route('/<path:path>')
async def static_pages(path):
    if '..' in path:
        return 'no', 404

    static_path = Path.cwd() / Path('static') / path
    return await app.send_static_file(str(static_path))
