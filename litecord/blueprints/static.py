from quart import Blueprint, current_app as app
from pathlib import Path

bp = Blueprint('static', __name__)


@bp.route('/<path:path>')
async def static_pages(path):
    return app.send_static_file(str(Path(f'./static/{path}')))
