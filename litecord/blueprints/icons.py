"""

Litecord
Copyright (C) 2018-2019  Luna Mendes

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""

from os.path import splitext
from quart import Blueprint, current_app as app, send_file

bp = Blueprint('images', __name__)


async def send_icon(scope, key, icon_hash, **kwargs):
    """Send an icon."""
    icon = await app.icons.generic_get(
        scope, key, icon_hash, **kwargs)

    if not icon:
        return '', 404

    return await send_file(icon.as_path)


def splitext_(filepath):
    name, ext = splitext(filepath)
    return name, ext.strip('.')


@bp.route('/emojis/<emoji_file>', methods=['GET'])
async def _get_raw_emoji(emoji_file):
    # emoji = app.icons.get_emoji(emoji_id, ext=ext)
    # just a test file for now
    emoji_id, ext = splitext_(emoji_file)
    return await send_icon(
        'emoji', emoji_id, None, ext=ext)


@bp.route('/icons/<int:guild_id>/<icon_file>', methods=['GET'])
async def _get_guild_icon(guild_id: int, icon_file: str):
    icon_hash, ext = splitext_(icon_file)
    return await send_icon('guild', guild_id, icon_hash, ext=ext)


@bp.route('/embed/avatars/<int:discrim>.png')
async def _get_default_user_avatar(discrim: int):
    pass


@bp.route('/avatars/<int:user_id>/<avatar_file>')
async def _get_user_avatar(user_id, avatar_file):
    avatar_hash, ext = splitext_(avatar_file)
    return await send_icon('user', user_id, avatar_hash, ext=ext)


# @bp.route('/app-icons/<int:application_id>/<icon_hash>.<ext>')
async def get_app_icon(application_id, icon_hash, ext):
    pass


@bp.route('/channel-icons/<int:channel_id>/<icon_file>', methods=['GET'])
async def _get_gdm_icon(channel_id: int, icon_file: str):
    icon_hash, ext = splitext_(icon_file)
    return await send_icon('channel-icons', channel_id, icon_hash, ext=ext)


@bp.route('/splashes/<int:guild_id>/<icon_file>', methods=['GET'])
async def _get_guild_splash(guild_id: int, icon_file: str):
    icon_hash, ext = splitext_(icon_file)
    return await send_icon('splash', guild_id, icon_hash, ext=ext)


@bp.route('/banners/<int:guild_id>/<icon_file>', methods=['GET'])
async def _get_guild_banner(guild_id: int, icon_file: str):
    icon_hash, ext = splitext_(icon_file)
    return await send_icon('banner', guild_id, icon_hash, ext=ext)
