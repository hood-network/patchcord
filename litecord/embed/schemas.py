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

"""
litecord.embed.schemas - embed input validators.
"""
import urllib.parse
from litecord.types import Color


class EmbedURL:
    def __init__(self, url: str):
        parsed = urllib.parse.urlparse(url)

        if parsed.scheme not in ("http", "https", "attachment"):
            raise ValueError("Invalid URL scheme")

        self.scheme = parsed.scheme
        self.raw_url = url
        self.parsed = parsed

    @classmethod
    def from_parsed(cls, parsed):
        """Make an EmbedURL instance out of an already parsed 6-tuple."""
        return cls(parsed.geturl())

    @property
    def url(self) -> str:
        """Return the unparsed URL."""
        return urllib.parse.urlunparse(self.parsed)

    @property
    def to_json(self) -> str:
        """'json' version of the url."""
        return self.url

    @property
    def to_md_path(self) -> str:
        """Convert the EmbedURL to a mediaproxy path (post img/meta)."""
        parsed = self.parsed
        return f"{parsed.scheme}/{parsed.netloc}" f"{parsed.path}?{parsed.query}"


EMBED_FOOTER = {
    "text": {"type": "string", "minlength": 1, "maxlength": 1024, "required": True},
    "icon_url": {"coerce": EmbedURL, "required": False},
    # NOTE: proxy_icon_url set by us
}

EMBED_IMAGE = {
    "url": {"coerce": EmbedURL, "required": True},
    # NOTE: proxy_url, width, height set by us
}

EMBED_THUMBNAIL = EMBED_IMAGE

EMBED_AUTHOR = {
    "name": {"type": "string", "minlength": 1, "maxlength": 256, "required": False},
    "url": {"coerce": EmbedURL, "required": False},
    "icon_url": {"coerce": EmbedURL, "required": False}
    # NOTE: proxy_icon_url set by us
}

EMBED_FIELD = {
    "name": {"type": "string", "minlength": 1, "maxlength": 256, "required": True},
    "value": {"type": "string", "minlength": 1, "maxlength": 1024, "required": True},
    "inline": {"type": "boolean", "required": False, "default": True},
}

EMBED_OBJECT = {
    "type": {"type": "string", "minlength": 1, "maxlength": 256, "required": False},
    "title": {"type": "string", "minlength": 1, "maxlength": 256, "required": False},
    # NOTE: type set by us
    "description": {
        "type": "string",
        "minlength": 1,
        "maxlength": 2048,
        "required": False,
    },
    "url": {"coerce": EmbedURL, "required": False},
    "timestamp": {
        # TODO: an ISO 8601 type
        # TODO: maybe replace the default in here with now().isoformat?
        "type": "string",
        "required": False,
    },
    "color": {"coerce": Color, "required": False},
    "footer": {"type": "dict", "schema": EMBED_FOOTER, "required": False},
    "image": {"type": "dict", "schema": EMBED_IMAGE, "required": False},
    "thumbnail": {"type": "dict", "schema": EMBED_THUMBNAIL, "required": False},
    # NOTE: 'video' set by us
    # NOTE: 'provider' set by us
    "author": {"type": "dict", "schema": EMBED_AUTHOR, "required": False},
    "fields": {
        "type": "list",
        "schema": {"type": "dict", "schema": EMBED_FIELD},
        "required": False,
    },
}
