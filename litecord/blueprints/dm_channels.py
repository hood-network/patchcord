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

from quart import Blueprint, request, current_app as app, jsonify
from logbook import Logger

from litecord.blueprints.auth import token_check
from litecord.blueprints.checks import channel_check
from litecord.enums import ChannelType

log = Logger(__name__)
bp = Blueprint('dm_channels', __name__)


@bp.route('/<int:dm_chan>/receipients/<int:user_id>', methods=['PUT'])
async def add_to_group_dm(dm_chan, user_id):
    """Adds a member to a group dm OR creates a group dm."""
    user_id = await token_check()
    ctype = await channel_check(
        user_id, dm_chan,
        only=[ChannelType.DM, ChannelType.GROUP_DM]
    )


@bp.route('/<int:dm_chan>/recipients/<int:user_id>', methods=['DELETE'])
async def remove_from_group_dm(dm_chan, user_id):
    """Remove users from group dm."""
    user_id = await token_check()
    ctype = await channel_check(
        user_id, dm_chan, only=ChannelType.GROUP_DM
    )
