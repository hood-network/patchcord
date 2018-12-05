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
        # TODO: should we check icon_url and convert it into
        # a proxied icon url?
        log.warning('embed with author.icon_url, ignoring')

    return embed
