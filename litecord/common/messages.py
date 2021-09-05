import json
import logging

from PIL import Image
from quart import request, current_app as app

from litecord.errors import BadRequest

log = logging.getLogger(__name__)


async def msg_create_request() -> tuple:
    """Extract the json input and any file information
    the client gave to us in the request.

    This only applies to create message route.
    """
    form = await request.form
    request_json = await request.get_json() or {}

    # NOTE: embed isn't set on form data
    json_from_form = {
        "content": form.get("content", ""),
        "nonce": form.get("nonce", "0"),
        "tts": json.loads(form.get("tts", "false")),
    }

    payload_json = json.loads(form.get("payload_json", "{}"))

    json_from_form.update(request_json)
    json_from_form.update(payload_json)

    files = await request.files

    for form_key, given_file in files.items():
        if given_file.content_length is None:
            raise BadRequest("Given file does not have content length.")

    # we don't really care about the given fields on the files dict, so
    # we only extract the values
    return json_from_form, [x for x in files.values()]


def msg_create_check_content(payload: dict, files: list, *, use_embeds=False):
    """Check if there is actually any content being sent to us."""
    has_content = bool(payload.get("content", ""))
    has_files = len(files) > 0

    embed_field = "embeds" if use_embeds else "embed"
    has_embed = embed_field in payload and payload.get(embed_field) is not None

    has_total_content = has_content or has_embed or has_files

    if not has_total_content:
        raise BadRequest("No content has been provided.")


async def msg_add_attachment(message_id: int, channel_id: int, attachment_file) -> int:
    """Add an attachment to a message.

    Parameters
    ----------
    message_id: int
        The ID of the message getting the attachment.
    channel_id: int
        The ID of the channel the message belongs to.

        Exists because the attachment URL scheme contains
        a channel id. The purpose is unknown, but we are
        implementing Discord's behavior.
    attachment_file: quart.FileStorage
        quart FileStorage instance of the file.
    """

    attachment_id = app.winter_factory.snowflake()
    filename = attachment_file.filename

    # understand file info
    mime = attachment_file.mimetype
    is_image = mime.startswith("image/")

    img_width, img_height = None, None

    # extract file size
    # it's possible a part does not contain content length.
    # do not let that pass on.
    file_size = attachment_file.content_length
    assert file_size is not None

    if is_image:
        # open with pillow, extract image size
        image = Image.open(attachment_file.stream)
        img_width, img_height = image.size

        # NOTE: DO NOT close the image, as closing the image will
        # also close the stream.

        # reset it to 0 for later usage
        attachment_file.stream.seek(0)

    await app.db.execute(
        """
        INSERT INTO attachments
            (id, channel_id, message_id,
             filename, filesize,
             image, width, height)
        VALUES
            ($1, $2, $3, $4, $5, $6, $7, $8)
        """,
        attachment_id,
        channel_id,
        message_id,
        filename,
        file_size,
        is_image,
        img_width,
        img_height,
    )

    ext = filename.split(".")[-1]

    with open(f"attachments/{attachment_id}.{ext}", "wb") as attach_file:
        attach_file.write(attachment_file.stream.read())

    log.debug("written {} bytes for attachment id {}", file_size, attachment_id)

    return attachment_id


async def msg_guild_text_mentions(
    payload: dict, guild_id: int, mentions_everyone: bool, mentions_here: bool
):
    """Calculates mention data side-effects."""
    # TODO this should be aware of allowed_mentions
    channel_id = int(payload["channel_id"])

    # calculate the user ids we'll bump the mention count for
    uids = set()

    # first is extracting user mentions
    for mention in payload["mentions"]:
        uids.add(int(mention["id"]))

    # then role mentions
    for role_mention in payload["mention_roles"]:
        role_id = int(role_mention)
        member_ids = await app.storage.get_role_members(role_id)

        for member_id in member_ids:
            uids.add(member_id)

    # at-here only updates the state
    # for the users that have a state
    # in the channel.
    if mentions_here:
        uids = set()

        await app.db.execute(
            """
        UPDATE user_read_state
        SET mention_count = mention_count + 1
        WHERE channel_id = $1
        """,
            channel_id,
        )

    # at-here updates the read state
    # for all users, including the ones
    # that might not have read permissions
    # to the channel.
    if mentions_everyone:
        uids = set()

        member_ids = await app.storage.get_member_ids(guild_id)

        await app.db.executemany(
            """
        UPDATE user_read_state
        SET mention_count = mention_count + 1
        WHERE channel_id = $1 AND user_id = $2
        """,
            [(channel_id, uid) for uid in member_ids],
        )

    for user_id in uids:
        await app.db.execute(
            """
        UPDATE user_read_state
        SET mention_count = mention_count + 1
        WHERE user_id = $1
            AND channel_id = $2
        """,
            user_id,
            channel_id,
        )


def message_view(message_data: dict) -> dict:
    # Change message type to 19 if this is a reply to another message
    if message_data["message_reference"] and request.discord_api_version > 7:
        return {**message_data, **{"type": 19}}
    return message_data
