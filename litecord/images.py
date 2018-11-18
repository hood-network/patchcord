import mimetypes
import asyncio
import base64

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from io import BytesIO

from logbook import Logger
from PIL import Image

IMAGE_FOLDER = Path('./images')
log = Logger(__name__)


def _get_ext(mime: str):
    extensions = mimetypes.guess_all_extensions(mime)
    return extensions[0].strip('.')


def _get_mime(ext: str):
    return mimetypes.types_map[f'.{ext}']


@dataclass
class Icon:
    """Main icon class"""
    key: str
    icon_hash: str
    mime: str

    @property
    def as_path(self) -> str:
        """Return a filesystem path for the given icon."""
        ext = _get_ext(self.mime)
        return str(IMAGE_FOLDER / f'{self.key}_{self.icon_hash}.{ext}')

    @property
    def as_pathlib(self) -> str:
        return Path(self.as_path)

    @property
    def extension(self) -> str:
        return _get_ext(self.mime)


class ImageError(Exception):
    """Image error class."""
    pass


def to_raw(data_type: str, data: str) -> bytes:
    """Given a data type in the data URI and data,
    give the raw bytes being encoded."""
    if data_type == 'base64':
        return base64.b64decode(data)

    return None


def _calculate_hash(fhandler) -> str:
    """Generate a hash of the given file.

    This calls the seek(0) of the file handler
    so it can be reused.

    Parameters
    ----------
    fhandler: file object
        Any file-like object.

    Returns
    -------
    str
        The SHA256 hash of the given file.
    """
    hash_obj = sha256()

    for chunk in iter(lambda: fhandler.read(4096), b''):
        hash_obj.update(chunk)

    # so that we can reuse the same handler
    # later on
    fhandler.seek(0)

    return hash_obj.hexdigest()


async def calculate_hash(fhandle, loop=None) -> str:
    """Calculate a hash of the given file handle.

    Uses run_in_executor to do the job asynchronously so
    the application doesn't lock up on large files.
    """
    if not loop:
        loop = asyncio.get_event_loop()

    fut = loop.run_in_executor(None, _calculate_hash, fhandle)
    return await fut


def parse_data_uri(string) -> tuple:
    """Extract image data."""
    try:
        header, headered_data = string.split(';')

        _, given_mime = header.split(':')
        data_type, data = headered_data.split(',')

        raw_data = to_raw(data_type, data)
        if raw_data is None:
            raise ImageError('Unknown data header')

        return given_mime, raw_data
    except ValueError:
        raise ImageError('data URI invalid syntax')


def _gen_update_sql(scope: str) -> str:
    field = {
        'user': 'avatar',
        'guild': 'icon'
    }[scope]

    table = {
        'user': 'users',
        'guild': 'guilds'
    }[scope]

    col = {
        'user': 'id',
        'guild': 'id'
    }[scope]

    return f"""
    SELECT {field} FROM {table} WHERE {col} = $1
    """


def _invalid(kwargs: dict):
    """Send an invalid value."""
    if not kwargs.get('always_icon', False):
        return None

    return Icon(None, None, '')


class IconManager:
    """Main icon manager."""
    def __init__(self, app):
        self.app = app
        self.storage = app.storage

    async def _convert_ext(self, icon: Icon, target: str):
        target_mime = _get_mime(target)
        log.info('converting from {} to {}', icon.mime, target_mime)

        target_path = IMAGE_FOLDER / f'{icon.key}_{icon.icon_hash}.{target}'

        if target_path.exists():
            return Icon(icon.key, icon.icon_hash, target_mime)

        image = Image.open(icon.as_path)
        target_fd = target_path.open('wb')
        image.save(target_fd, format=target)
        target_fd.close()

        return Icon(icon.key, icon.icon_hash, target_mime)

    async def generic_get(self, scope, key, icon_hash, **kwargs) -> Icon:
        """Get any icon."""
        log.debug('GET {} {} {}', scope, key, icon_hash)
        key = str(key)

        hash_query = 'AND hash = $3' if icon_hash else ''

        # hacky solution to only add icon_hash
        # when needed.
        args = [scope, key]

        if icon_hash:
            args.append(icon_hash)

        icon_row = await self.storage.db.fetchrow(f"""
        SELECT key, hash, mime
        FROM icons
        WHERE scope = $1
          AND key = $2
          {hash_query}
        """, *args)

        if not icon_row:
            return None

        icon = Icon(icon_row['key'], icon_row['hash'], icon_row['mime'])

        if not icon.as_pathlib.exists():
            await self.delete(icon)
            return None

        if 'ext' in kwargs and kwargs['ext'] != icon.extension:
            return await self._convert_ext(icon, kwargs['ext'])

        return icon

    async def get_guild_icon(self, guild_id: int, icon_hash: str, **kwargs):
        """Get an icon for a guild."""
        return await self.generic_get(
            'guild', guild_id, icon_hash, **kwargs)

    async def put(self, scope: str, key: str,
                  b64_data: str, **kwargs) -> Icon:
        """Insert an icon."""
        if b64_data is None:
            return _invalid(kwargs)

        mime, raw_data = parse_data_uri(b64_data)
        data_fd = BytesIO(raw_data)

        # get an extension for the given data uri
        extension = _get_ext(mime)

        if 'bsize' in kwargs and len(raw_data) > kwargs['bsize']:
            return _invalid(kwargs)

        if 'size' in kwargs:
            image = Image.open(data_fd)

            want = kwargs['size']

            log.info('resizing from {} to {}',
                     image.size, want)

            resized = image.resize(want)

            data_fd = BytesIO()
            resized.save(data_fd, format=extension)

            # reseek to copy it to raw_data
            data_fd.seek(0)
            raw_data = data_fd.read()

            data_fd.seek(0)

        # calculate sha256
        # ignore icon hashes if we're talking about emoji
        icon_hash = (await calculate_hash(data_fd)
                     if scope != 'emoji'
                     else None)

        await self.storage.db.execute("""
        INSERT INTO icons (scope, key, hash, mime)
        VALUES ($1, $2, $3, $4)
        """, scope, str(key), icon_hash, mime)

        # write it off to fs
        icon_path = IMAGE_FOLDER / f'{key}_{icon_hash}.{extension}'
        icon_path.write_bytes(raw_data)

        # copy from data_fd to icon_fd
        # with icon_path.open(mode='wb') as icon_fd:
        #    icon_fd.write(data_fd.read())

        return Icon(str(key), icon_hash, mime)

    async def delete(self, icon: Icon):
        """Delete an icon from the database and filesystem."""
        if not icon:
            return

        # dereference
        await self.storage.db.execute("""
        UPDATE users
        SET avatar = NULL
        WHERE avatar = $1
        """, icon.icon_hash)

        await self.storage.db.execute("""
        UPDATE group_dm_channels
        SET icon = NULL
        WHERE icon = $1
        """, icon.icon_hash)

        await self.storage.db.execute("""
        DELETE FROM guild_emoji
        WHERE image = $1
        """, icon.icon_hash)

        await self.storage.db.execute("""
        UPDATE guilds
        SET icon = NULL
        WHERE icon = $1
        """, icon.icon_hash)

        await self.storage.db.execute("""
        DELETE FROM icons
        WHERE hash = $1
        """, icon.icon_hash)

        paths = IMAGE_FOLDER.glob(f'{icon.key}_{icon.icon_hash}.*')

        for path in paths:
            try:
                path.unlink()
            except FileNotFoundError:
                pass

    async def update(self, scope: str, key: str,
                     new_icon_data: str, **kwargs) -> Icon:
        """Update an icon on a key."""
        old_icon_hash = await self.storage.db.fetchval(
            _gen_update_sql(scope), key)

        key = str(key)
        old_icon = await self.generic_get(scope, key, old_icon_hash)
        await self.delete(old_icon)

        return await self.put(scope, key, new_icon_data, **kwargs)
