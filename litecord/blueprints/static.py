from quart import Blueprint, current_app as app, render_template_string
from pathlib import Path

bp = Blueprint('static', __name__)


@bp.route('/<path:path>')
async def static_pages(path):
    """Map requests from / to /static."""
    if '..' in path:
        return 'no', 404

    static_path = Path.cwd() / Path('static') / path
    return await app.send_static_file(str(static_path))


@bp.route('/')
@bp.route('/api')
async def index_handler():
    """Handler for the index page."""
    index_path = Path.cwd() / Path('static') / 'index.html'
    return await render_template_string(
        index_path.read_text(), inst_name=app.config['NAME'])
