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

import re
import asyncio

from logbook import Logger

from litecord.embed.sanitizer import proxify, fetch_metadata

log = Logger(__name__)


async def process_url_embed(config, storage, dispatcher,
                            session, payload: dict, *, delay=0):
    """Process URLs in a message and generate embeds based on that."""
    await asyncio.sleep(delay)

    message_id = int(payload['id'])
    channel_id = int(payload['channel_id'])

    # if we already have embeds
    # we shouldn't add our own.
    embeds = payload['embeds']

    if embeds:
        log.debug('url processor: ignoring existing embeds @ mid {}',
                  message_id)
        return

    # use regex to get URLs
    urls = re.findall(r'(https?://\S+)', payload['content'])
    urls = urls[:5]

    new_embeds = []

    # fetch metadata for each url
    for url in urls:
        img_proxy_url = proxify(url, config=config)
        meta = await fetch_metadata(url, config=config, session=session)

        if meta is None:
            continue

        if not meta['image']:
            continue

        new_embeds.append({
            'type': 'image',
            'url': url,
            'thumbnail': {
                'width': meta['width'],
                'height': meta['height'],
                'url': url,
                'proxy_url': img_proxy_url
            }
        })

    # update if we got embeds
    if not new_embeds:
        return

    log.debug('made {} thumbnail embeds for mid {}',
              len(new_embeds), message_id)

    await storage.execute_with_json("""
    UPDATE messages
    SET embeds = $1
    WHERE messages.id = $2
    """, new_embeds, message_id)

    update_payload = {
        'id': str(message_id),
        'channel_id': str(channel_id),
        'embeds': new_embeds,
    }

    if 'guild_id' in payload:
        update_payload['guild_id'] = payload['guild_id']

    await dispatcher.dispatch(
        'channel', channel_id, 'MESSAGE_UPDATE', update_payload)
