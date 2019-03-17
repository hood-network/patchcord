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

from typing import Dict, Any, Optional

from quart import Blueprint, jsonify, current_app as app, request

from litecord.auth import token_check
from litecord.blueprints.checks import channel_check, channel_perm_check

from litecord.schemas import validate, WEBHOOK_CREATE
from litecord.enums import ChannelType
from litecord.snowflake import get_snowflake
from litecord.utils import async_map

bp = Blueprint('webhooks', __name__)


async def get_webhook(webhook_id: int) -> Optional[Dict[str, Any]]:
    """Get a webhook data"""
    row = await app.db.fetchrow("""
    SELECT id::text, guild_id::text, channel_id::text, creator_id
           name, avatar, token
    FROM webhooks
    WHERE id = $1
    """, webhook_id)

    if not row:
        return None

    drow = dict(row)

    drow['user'] = await app.storage.get_user(row['creator_id'])
    drow.pop('creator_id')

    return drow


async def _webhook_check():
    user_id = await token_check()

    await channel_check(user_id, channel_id, ChannelType.GUILD_TEXT)
    await channel_perm_check(user_id, channel_id, 'manage_webhooks')

    return user_id


@bp.route('/channels/<int:channel_id>/webhooks', methods=['POST'])
async def create_webhook(channel_id: int):
    """Create a webhook given a channel."""
    user_id = await _webhook_check()

    j = validate(await request.get_json(), WEBHOOK_CREATE)

    guild_id = await app.storage.guild_from_channel(channel_id)

    webhook_id = get_snowflake()
    token = 'asd'

    await app.db.execute(
        """
        INSERT INTO webhooks
            (id, guild_id, channel_id, creator_id, name, avatar, token)
        VALUES
            ($1, $2, $3, $4, $5, $6, $7)
        """,
        webhook_id, guild_id, channel_id, user_id,
        j['name'], j.get('avatar'), token
    )

    return jsonify(await get_webhook(webhook_id))


@bp.route('/channels/<int:channel_id>/webhooks', methods=['GET'])
async def get_channel_webhook(channel_id: int):
    """Get a list of webhooks in a channel"""
    _user_id = await _webhook_check()

    webhook_ids = await app.db.fetch("""
    SELECT id
    FROM webhooks
    WHERE channel_id = $1
    """, channel_id)

    webhook_ids = [r['id'] for r in webhook_ids]

    return jsonify(
        await async_map(get_webhook, webhook_ids)
    )


@bp.route('/guilds/<int:guild_id>/webhooks', methods=['GET'])
async def get_guild_webhook(guild_id):
    pass


@bp.route('/webhooks/<int:webhook_id>', methods=['GET'])
async def get_single_webhook(webhook_id):
    pass


@bp.route('/webhooks/<int:webhook_id>/<webhook_token>', methods=['GET'])
async def get_tokened_webhook(webhook_id, webhook_token):
    pass


@bp.route('/webhooks/<int:webhook_id>', methods=['PATCH'])
async def modify_webhook(webhook_id):
    pass


@bp.route('/webhooks/<int:webhook_id>/<webhook_token>', methods=['PATCH'])
async def modify_webhook_tokened(webhook_id, webhook_token):
    pass


@bp.route('/webhooks/<int:webhook_id>', methods=['DELETE'])
async def del_webhook(webhook_id):
    pass


@bp.route('/webhooks/<int:webhook_id>/<webhook_token>', methods=['DELETE'])
async def del_webhook_tokened(webhook_id, webhook_token):
    pass


@bp.route('/webhooks/<int:webhook_id>/<webhook_token>', methods=['POST'])
async def execute_webhook(webhook_id, webhook_token):
    pass


@bp.route('/webhooks/<int:webhook_id>/<webhook_token>/slack',
          methods=['POST'])
async def execute_slack_webhook(webhook_id, webhook_token):
    pass


@bp.route('/webhooks/<int:webhook_id>/<webhook_token>/github', methods=['POST'])
async def execute_github_webhook(webhook_id, webhook_token):
    pass
