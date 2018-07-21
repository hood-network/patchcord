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
