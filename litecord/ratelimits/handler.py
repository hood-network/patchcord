from quart import current_app as app, request

from litecord.errors import Ratelimited
from litecord.auth import token_check, Unauthorized


async def _check_bucket(bucket):
    retry_after = bucket.update_rate_limit()

    request.bucket = bucket

    if retry_after:
        request.retry_after = retry_after

        raise Ratelimited('You are being rate limited.', {
            'retry_after': int(retry_after * 1000),
            'global': request.bucket_global,
        })


async def _handle_global(ratelimit):
    """Global ratelimit is per-user."""
    try:
        user_id = await token_check()
    except Unauthorized:
        user_id = request.remote_addr

    request.bucket_global = True
    bucket = ratelimit.get_bucket(user_id)
    await _check_bucket(bucket)


async def _handle_specific(ratelimit):
    try:
        user_id = await token_check()
    except Unauthorized:
        user_id = request.remote_addr

    # construct the key based on the ratelimit.keys
    keys = ratelimit.keys

    # base key is the user id
    key_components = [f'user_id:{user_id}']

    for key in keys:
        val = request.view_args[key]
        key_components.append(f'{key}:{val}')

    bucket_key = ':'.join(key_components)
    bucket = ratelimit.get_bucket(bucket_key)
    await _check_bucket(bucket)


async def ratelimit_handler():
    """Main ratelimit handler.

    Decides on which ratelimit to use.
    """
    rule = request.url_rule

    if rule is None:
        return await _handle_global(
            app.ratelimiter.global_bucket
        )

    # rule.endpoint is composed of '<blueprint>.<function>'
    # and so we can use that to make routes with different
    # methods have different ratelimits
    rule_path = rule.endpoint

    # some request ratelimit context.
    # TODO: maybe put those in a namedtuple or contextvar of sorts?
    request.bucket = None
    request.retry_after = None
    request.bucket_global = False

    try:
        ratelimit = app.ratelimiter.get_ratelimit(rule_path)
        await _handle_specific(ratelimit)
    except KeyError:
        await _handle_global(
            app.ratelimiter.global_bucket
        )
