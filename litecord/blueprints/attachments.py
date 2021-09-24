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

from pathlib import Path

from quart import Blueprint, send_file, current_app as app, request
from PIL import Image

from litecord.images import resize_gif

bp = Blueprint("attachments", __name__)
ATTACHMENTS = Path.cwd() / "attachments"


async def _resize_gif(
    attach_id: int, resized_path: Path, width: int, height: int
) -> str:
    """Resize a GIF attachment."""

    # get original gif bytes
    orig_path = ATTACHMENTS / f"{attach_id}.gif"
    orig_bytes = orig_path.read_bytes()

    # give them and the target size to the
    # image module's resize_gif

    _data_fd, raw_data = await resize_gif(orig_bytes, (width, height))

    # write raw_data to the destination
    resized_path.write_bytes(raw_data)

    return str(resized_path)


FORMAT_HARDCODE = {"jpg": "jpeg", "jpe": "jpeg"}


def to_format(ext: str) -> str:
    """Return a proper format string for Pillow consumption."""
    ext = ext.lower()

    if ext in FORMAT_HARDCODE:
        return FORMAT_HARDCODE[ext]

    return ext


async def _resize(image, attach_id: int, ext: str, width: int, height: int) -> str:
    """Resize an image."""
    # check if we have it on the folder
    resized_path = ATTACHMENTS / f"{attach_id}_{width}_{height}.{ext}"

    # keep a str-fied instance since that is what
    # we'll return.
    resized_path_s = str(resized_path)

    if resized_path.exists():
        return resized_path_s

    # if we dont, we need to generate it off the
    # given image instance.

    # the process is different for gif files because we need
    # gifsicle. doing it manually is too troublesome.
    if ext == "gif":
        return await _resize_gif(attach_id, resized_path, width, height)

    # NOTE: this is the same resize mode for icons.
    resized = image.resize((width, height), resample=Image.LANCZOS)
    resized.save(resized_path_s, format=to_format(ext))

    return resized_path_s


@bp.route(
    "/attachments" "/<int:channel_id>/<int:message_id>/<filename>", methods=["GET"]
)
async def _get_attachment(channel_id: int, message_id: int, filename: str):

    attach_id = await app.db.fetchval(
        """
    SELECT id
    FROM attachments
    WHERE channel_id = $1
      AND message_id = $2
      AND filename = $3
    """,
        channel_id,
        message_id,
        filename,
    )

    if attach_id is None:
        return "", 404

    ext = filename.split(".")[-1]
    filepath = f"./attachments/{attach_id}.{ext}"

    image = Image.open(filepath)
    im_width, im_height = image.size

    try:
        width = int(request.args.get("width", 0)) or im_width
    except ValueError:
        return "", 400

    try:
        height = int(request.args.get("height", 0)) or im_height
    except ValueError:
        return "", 400

    # if width and height are the same (happens if they weren't provided)
    if width == im_width and height == im_height:
        return await send_file(filepath)

    # resize image
    new_filepath = await _resize(image, attach_id, ext, width, height)
    return await send_file(new_filepath)
