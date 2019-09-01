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
import urllib.parse
from pathlib import Path

from logbook import Logger

from litecord.embed.sanitizer import proxify, fetch_metadata, fetch_embed
from litecord.embed.schemas import EmbedURL

log = Logger(__name__)


MEDIA_EXTENSIONS = (
    'png',
    'jpg', 'jpeg',
    'gif', 'webm'
)


async def insert_media_meta(url, config, session):
    """Insert media metadata as an embed."""
    img_proxy_url = proxify(url, config=config)
    meta = await fetch_metadata(url, config=config, session=session)

    if meta is None:
        return

    if not meta['image']:
        return

    return {
        'type': 'image',
        'url': url,
        'thumbnail': {
            'width': meta['width'],
            'height': meta['height'],
            'url': url,
            'proxy_url': img_proxy_url
        }
    }


async def msg_update_embeds(payload, new_embeds, storage, dispatcher):
    """Update the message with the given embeds and dispatch a MESSAGE_UPDATE
    to users."""

    message_id = int(payload['id'])
    channel_id = int(payload['channel_id'])

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

    if 'flags' in payload:
        update_payload['flags'] = payload['flags']

    await dispatcher.dispatch(
        'channel', channel_id, 'MESSAGE_UPDATE', update_payload)


def is_media_url(url) -> bool:
    """Return if the given URL is a media url."""

    if isinstance(url, EmbedURL):
        parsed = url.parsed
    else:
        parsed = urllib.parse.urlparse(url)

    path = Path(parsed.path)
    extension = path.suffix.lstrip('.')

    return extension in MEDIA_EXTENSIONS


async def insert_mp_embed(parsed, config, session):
    """Insert mediaproxy embed."""
    embed = await fetch_embed(parsed, config=config, session=session)
    return embed


async def process_url_embed(config, storage, dispatcher,
                            session, payload: dict, *, delay=0):
    """Process URLs in a message and generate embeds based on that."""
    await asyncio.sleep(delay)

    message_id = int(payload['id'])

    # if we already have embeds
    # we shouldn't add our own.
    embeds = payload['embeds']

    if embeds:
        log.debug('url processor: ignoring existing embeds @ mid {}',
                  message_id)
        return

    # now, we have two types of embeds:
    # - image embeds
    # - url embeds

    # use regex to get URLs
    urls = re.findall(r'(https?://\S+)', payload['content'])
    urls = urls[:5]

    # from there, we need to parse each found url and check its path.
    # if it ends with png/jpg/gif/some other extension, we treat it as
    # media metadata to fetch.

    # if it isn't, we forward an /embed/ scope call to mediaproxy
    # to generate an embed for us out of the url.

    new_embeds = []

    for url in urls:
        url = EmbedURL(url)

        if is_media_url(url):
            embed = await insert_media_meta(url, config, session)
        else:
            embed = await insert_mp_embed(url, config, session)

        if not embed:
            continue

        new_embeds.append(embed)

    # update if we got embeds
    if not new_embeds:
        return

    log.debug('made {} embeds for mid {}',
              len(new_embeds), message_id)

    await msg_update_embeds(payload, new_embeds, storage, dispatcher)
