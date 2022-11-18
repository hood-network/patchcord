import json
import os
from typing import Optional, TYPE_CHECKING

from litecord.enums import PremiumType
from litecord.errors import BadRequest, ManualFormError, TooLarge
from logbook import Logger
from PIL import Image

if TYPE_CHECKING:
    from litecord.typing_hax import app, request
else:
    from quart import current_app as app, request

log = Logger(__name__)

PLAN_ID_TO_TYPE = {
    "premium_month_tier_0": PremiumType.TIER_0,
    "premium_month_tier_1": PremiumType.TIER_1,
    "premium_month_tier_2": PremiumType.TIER_2,
    "premium_year_tier_1": PremiumType.TIER_1,
    "premium_year_tier_2": PremiumType.TIER_2,
}


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
        "nonce": form.get("nonce", ""),
        "tts": json.loads(form.get("tts", "false")),
    }

    payload_json = json.loads(form.get("payload_json", "{}"))

    json_from_form.update(request_json)
    json_from_form.update(payload_json)

    files = await request.files

    for num, (_, given_file) in enumerate(files.items()):
        if given_file.content_length is None:
            raise ManualFormError(
                files={
                    num: {
                        "content_length": {
                            "code": "BASE_TYPE_REQUIRED",
                            "message": "This field is required.",
                        }
                    }
                }
            )

    if len(files) > 10:
        raise ManualFormError(
            files={
                "code": "BASE_TYPE_MAX_LENGTH",
                "message": "Must be 10 or fewer in length.",
            }
        )

    # we don't really care about the given fields on the files dict, so
    # we only extract the values
    return json_from_form, [x for x in files.values()]


def msg_create_check_content(payload: dict, files: list):
    """Check if there is actually any content being sent to us."""
    content = payload["content"] or ""
    embeds = (
        (payload.get("embeds") or []) or [payload["embed"]]
        if "embed" in payload and payload["embed"]
        else []
    )
    sticker_ids = payload.get("sticker_ids")
    if not content and not embeds and not sticker_ids and not files:
        raise BadRequest(50006)


async def msg_add_attachment(
    message_id: int, channel_id: int, author_id: Optional[int], attachment_file
) -> int:
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
    author_id: Optional[int]
        The ID of the author of the message.
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

    if is_image:
        # open with pillow, extract image size
        image = Image.open(attachment_file.stream)
        img_width, img_height = image.size

        # NOTE: DO NOT close the image, as closing the image will
        # also close the stream.

        # reset it to 0 for later usage
        attachment_file.stream.seek(0)

    if not file_size:
        attachment_file.stream.seek(0, os.SEEK_END)
        file_size = attachment_file.stream.tell()
        attachment_file.stream.seek(0)

    max_size = 8 * 1024 * 1024
    if author_id:
        plan_id = await app.db.fetchval(
            """
        SELECT payment_gateway_plan_id
        FROM user_subscriptions
        WHERE status = 1
            AND user_id = $1
        """,
            author_id,
        )
        premium_type = PLAN_ID_TO_TYPE.get(plan_id)
        if premium_type == 0:
            max_size = 20 * 1024 * 1024
        elif premium_type == 1:
            max_size = 50 * 1024 * 1024
        elif premium_type == 2:
            max_size = 500 * 1024 * 1024

    if file_size > max_size:
        raise TooLarge()

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
