from quart import Blueprint, current_app as app, send_file

bp = Blueprint('images', __name__)


@bp.route('/emojis/<int:emoji_id>.<ext>', methods=['GET'])
async def get_raw_emoji(emoji_id: int, ext: str):
    # emoji = app.icons.get_emoji(emoji_id, ext=ext)
    # just a test file for now
    return await send_file('./LICENSE')


@bp.route('/icons/<int:guild_id>/<icon_hash>.<ext>', methods=['GET'])
async def get_guild_icon(guild_id: int, icon_hash: str, ext: str):
    pass


@bp.route('/splashes/<int:guild_id>/<icon_hash>.<ext>', methods=['GET'])
async def get_guild_splash(guild_id: int, splash_hash: str, ext: str):
    pass


@bp.route('/embed/avatars/<int:discrim>.png')
async def get_default_user_avatar(discrim: int):
    pass


@bp.route('/avatars/<int:user_id>/<avatar_hash>.<ext>')
async def get_user_avatar(user_id, avatar_hash, ext):
    pass


# @bp.route('/app-icons/<int:application_id>/<icon_hash>.<ext>')
async def get_app_icon(application_id, icon_hash, ext):
    pass
