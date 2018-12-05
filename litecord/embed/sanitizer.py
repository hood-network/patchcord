"""
litecord.embed.sanitizer
    sanitize embeds by giving common values
    such as type: rich
"""
from typing import Dict, Any
from logbook import Logger

from litecord.embed.schemas import EmbedURL

log = Logger(__name__)
Embed = Dict[str, Any]


def _sane(v):
    if isinstance(v, EmbedURL):
        return v.to_json

    return v


def sanitize_embed(embed: Embed) -> Embed:
    """Sanitize an embed object."""
    return {**embed, **{
        'type': 'rich'
    }}


def path_exists(embed: Embed, components: str):
    """Tell if a given path exists in an embed.

    The components string is formatted like this:
        key1.key2.key3.key4. <...> .keyN

    with each key going deeper and deeper into the embed.
    """
    if isinstance(components, str):
        components = components.split('.')
    else:
        components = list(components)

    if not components:
        return True

    current = components[0]

    if current in embed:
        return path_exists(embed[current], components[1:])

    return False


async def fill_embed(embed: Embed) -> Embed:
    """Fill an embed with more information."""
    embed = sanitize_embed(embed)

    if path_exists(embed, 'footer.icon_url'):
        # TODO: make proxy_icon_url
        log.warning('embed with footer.icon_url, ignoring')

    if path_exists(embed, 'image.url'):
        # TODO: make proxy_icon_url, width, height
        log.warning('embed with footer.image_url, ignoring')

    if path_exists(embed, 'author.icon_url'):
        log.warning('embed with author.icon_url, ignoring')

    return embed
