from .gateway import bp as gateway
from .auth import bp as auth
from .users import bp as users
from .guilds import bp as guilds
from .channels import bp as channels
from .webhooks import bp as webhooks
from .science import bp as science
from .voice import bp as voice
from .invites import bp as invites
from .relationships import bp as relationships
from .dms import bp as dms
from .icons import bp as icons

__all__ = ['gateway', 'auth', 'users', 'guilds', 'channels',
           'webhooks', 'science', 'voice', 'invites', 'relationships',
           'dms', 'icons']
