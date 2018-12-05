"""
litecord.embed.schemas - embed input validators.
"""
import urllib.parse
from litecord.types import Color


class EmbedURL:
    def __init__(self, url: str):
        parsed = urllib.parse.urlparse(url)

        if parsed.scheme not in ('http', 'https', 'attachment'):
            raise ValueError('Invalid URL scheme')

        self.raw_url = url
        self.parsed = parsed

    @property
    def url(self):
        """Return the URL."""
        return urllib.parse.urlunparse(self.parsed)

    @property
    def to_json(self):
        return self.url


EMBED_FOOTER = {
    'text': {
        'type': 'string', 'minlength': 1, 'maxlength': 128, 'required': True},

    'icon_url': {
        'coerce': EmbedURL, 'required': False,
    },

    # NOTE: proxy_icon_url set by us
}

EMBED_IMAGE = {
    'url': {'coerce': EmbedURL, 'required': True},

    # NOTE: proxy_url, width, height set by us
}

EMBED_THUMBNAIL = EMBED_IMAGE

EMBED_AUTHOR = {
    'name': {
        'type': 'string', 'minlength': 1, 'maxlength': 128, 'required': False
    },
    'url': {
        'coerce': EmbedURL, 'required': False,
    },
    'icon_url': {
        'coerce': EmbedURL, 'required': False,
    }
}

EMBED_FIELD = {
    'name': {
        'type': 'string', 'minlength': 1, 'maxlength': 128, 'required': True
    },
    'value': {
        'type': 'string', 'minlength': 1, 'maxlength': 128, 'required': True
    },
    'inline': {
        'type': 'boolean', 'required': False, 'default': True,
    },
}

EMBED_OBJECT = {
    'title': {
        'type': 'string', 'minlength': 1, 'maxlength': 128, 'required': False},
    # NOTE: type set by us
    'description': {
        'type': 'string', 'minlength': 1, 'maxlength': 1024, 'required': False,
    },
    'url': {
        'coerce': EmbedURL, 'required': False,
    },
    'timestamp': {
        # TODO: an ISO 8601 type
        # TODO: maybe replace the default in here with now().isoformat?
        'type': 'string', 'required': False
    },

    'color': {
        'coerce': Color, 'required': False
    },

    'footer': {
        'type': 'dict',
        'schema': EMBED_FOOTER,
        'required': False,
    },
    'image': {
        'type': 'dict',
        'schema': EMBED_IMAGE,
        'required': False,
    },
    'thumbnail': {
        'type': 'dict',
        'schema': EMBED_THUMBNAIL,
        'required': False,
    },

    # NOTE: 'video' set by us
    # NOTE: 'provider' set by us

    'author': {
        'type': 'dict',
        'schema': EMBED_AUTHOR,
        'required': False,
    },

    'fields': {
        'type': 'list',
        'schema': {'type': 'dict', 'schema': EMBED_FIELD},
        'required': False,
    },
}
