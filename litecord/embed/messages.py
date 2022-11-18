"""

Litecord
Copyright (C) 2018-2021  Luna Mendes and Litecord Contributors

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
from typing import List, Optional, TYPE_CHECKING

from logbook import Logger

from litecord.embed.sanitizer import proxify, fetch_metadata, fetch_mediaproxy_embed
from litecord.embed.schemas import EmbedURL
from litecord.enums import MessageFlags

if TYPE_CHECKING:
    from litecord.typing_hax import app
else:
    from quart import current_app as app

log = Logger(__name__)


MEDIA_EXTENSIONS = ("png", "jpg", "jpeg", "gif", "webm")


async def fetch_mediaproxy_img_meta(url) -> Optional[dict]:
    """Insert media metadata as an embed."""
    img_proxy_url = proxify(url)
    meta = await fetch_metadata(url)

    if meta is None:
        return None

    if not meta["image"]:
        return None

    return {
        "type": "image",
        "url": url,
        "thumbnail": {
            "width": meta["width"],
            "height": meta["height"],
            "url": url,
            "proxy_url": img_proxy_url,
        },
    }


async def msg_update_embeds(payload, new_embeds):
    """Update the message with the given embeds and dispatch a MESSAGE_UPDATE
    to users."""

    message_id = int(payload["id"])
    channel_id = int(payload["channel_id"])

    await app.storage.execute_with_json(
        """
        UPDATE messages
        SET embeds = $1
        WHERE messages.id = $2
        """,
        new_embeds,
        message_id,
    )

    update_payload = {
        "id": str(message_id),
        "channel_id": str(channel_id),
        "embeds": new_embeds,
    }

    if "guild_id" in payload:
        update_payload["guild_id"] = payload["guild_id"]

    if "flags" in payload:
        update_payload["flags"] = payload["flags"]

    await app.dispatcher.channel.dispatch(
        channel_id, ("MESSAGE_UPDATE", update_payload)
    )


def is_media_url(url) -> bool:
    """Return if the given URL is a media url."""

    if isinstance(url, EmbedURL):
        parsed = url.parsed
    else:
        parsed = urllib.parse.urlparse(url)

    path = Path(parsed.path)
    extension = path.suffix.lstrip(".")

    return extension in MEDIA_EXTENSIONS


async def process_url_embed(payload: dict, *, delay=0):
    """Process URLs in a message and generate embeds based on that."""
    await asyncio.sleep(delay)

    message_id = int(payload["id"])

    # if suppress embeds is set
    # we shouldn't add our own.
    suppress = MessageFlags.from_int(payload.get("flags", 0)).is_suppress_embeds
    if suppress:
        log.debug("url processor: ignoring suppressed embeds @ mid {}", message_id)
        return

    # use regex to get URLs
    urls = re.findall(r"(https?://\S+)", payload["content"])
    urls = urls[:5]

    # from there, we need to parse each found url and check its path.
    # if it ends with png/jpg/gif/some other extension, we treat it as
    # media metadata to fetch.

    # if it isn't, we forward an /embed/ scope call to mediaproxy
    # to generate an embed for us out of the url.

    new_embeds: List[dict] = []

    for upstream_url in urls:
        url = EmbedURL(upstream_url)

        if is_media_url(url):
            embed = await fetch_mediaproxy_img_meta(url)
            if embed is not None:
                embeds = [embed]
        else:
            embeds = await fetch_mediaproxy_embed(url)

        if not embeds:
            continue

        new_embeds.extend(embeds)

    # update if we got embeds
    if not new_embeds:
        return

    log.debug("made {} embeds for mid {}", len(new_embeds), message_id)

    await msg_update_embeds(payload, payload.get("embeds", []) + new_embeds)
