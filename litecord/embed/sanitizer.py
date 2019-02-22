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

"""
litecord.embed.sanitizer
    sanitize embeds by giving common values
    such as type: rich
"""
from typing import Dict, Any

from logbook import Logger
from quart import current_app as app

from litecord.embed.schemas import EmbedURL

log = Logger(__name__)
Embed = Dict[str, Any]


def sanitize_embed(embed: Embed) -> Embed:
    """Sanitize an embed object.

    This is non-complex sanitization as it doesn't
    need the app object.
    """
    return {**embed, **{
        'type': 'rich'
    }}


def path_exists(embed: Embed, components: str):
    """Tell if a given path exists in an embed (or any dictionary).

    The components string is formatted like this:
        key1.key2.key3.key4. <...> .keyN

    with each key going deeper and deeper into the embed.
    """

    # get the list of components given
    if isinstance(components, str):
        components = components.split('.')
    else:
        components = list(components)

    # if there are no components, we reached the end of recursion
    # and can return true
    if not components:
        return True

    # extract current component
    current = components[0]

    # if it exists, then we go down a level inside the dict
    # (via recursion)
    if current in embed:
        return path_exists(embed[current], components[1:])

    # if it doesn't exist, return False
    return False


def proxify(url, *, config=None) -> str:
    """Return a mediaproxy url for the given EmbedURL."""

    if not config:
        config = app.config

    if isinstance(url, str):
        url = EmbedURL(url)

    md_base_url = config['MEDIA_PROXY']
    parsed = url.parsed
    proto = 'https' if config['IS_SSL'] else 'http'

    return (
        # base mediaproxy url
        f'{proto}://{md_base_url}/img/'
        f'{parsed.scheme}/{parsed.netloc}{parsed.path}'
    )


async def fetch_metadata(url, *, config=None, session=None) -> dict:
    """Fetch metadata for a url."""

    if session is None:
        session = app.session

    if config is None:
        config = app.config

    if isinstance(url, str):
        url = EmbedURL(url)

    parsed = url.parsed

    md_path = f'{parsed.scheme}/{parsed.netloc}{parsed.path}'

    md_base_url = config['MEDIA_PROXY']
    proto = 'https' if config['IS_SSL'] else 'http'

    request_url = f'{proto}://{md_base_url}/meta/{md_path}'

    async with session.get(request_url) as resp:
        if resp.status != 200:
            body = await resp.text()

            log.warning('failed to generate meta for {!r}: {} {!r}',
                        url, resp.status, body)
            return

        return await resp.json()


async def fetch_embed(parsed, *, config=None, session=None) -> dict:
    """Fetch an embed"""

    if session is None:
        session = app.session

    if config is None:
        config = app.config

    # TODO: handle query string
    md_path = f'{parsed.scheme}/{parsed.netloc}{parsed.path}'

    md_base_url = config['MEDIA_PROXY']
    secure = 's' if config['IS_SSL'] else ''

    request_url = f'http{secure}://{md_base_url}/embed/{md_path}'

    async with session.get(request_url) as resp:
        if resp.status != 200:
            body = await resp.text()
            log.warning('failed to embed {!r}, {} {!r}',
                        parsed, resp.status, body)
            return

        return await resp.json()


async def fill_embed(embed: Embed) -> Embed:
    """Fill an embed with more information, such as proxy URLs."""
    embed = sanitize_embed(embed)

    if path_exists(embed, 'footer.icon_url'):
        embed['footer']['proxy_icon_url'] = \
            proxify(embed['footer']['icon_url'])

    if path_exists(embed, 'author.icon_url'):
        embed['author']['proxy_icon_url'] = \
            proxify(embed['author']['icon_url'])

    if path_exists(embed, 'image.url'):
        image_url = embed['image']['url']

        meta = await fetch_metadata(image_url)
        embed['image']['proxy_url'] = proxify(image_url)

        if meta and meta['image']:
            embed['image']['width'] = meta['width']
            embed['image']['height'] = meta['height']

    return embed
