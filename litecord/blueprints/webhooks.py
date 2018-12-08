"""

Litecord
Copyright (C) 2018  Luna Mendes

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

from quart import Blueprint

bp = Blueprint('webhooks', __name__)


@bp.route('/channels/<int:channel_id>/webhooks', methods=['POST'])
async def create_webhook(channel_id):
    pass


@bp.route('/channels/<int:channel_id>/webhooks', methods=['GET'])
async def get_channel_webhook(channel_id):
    pass


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
