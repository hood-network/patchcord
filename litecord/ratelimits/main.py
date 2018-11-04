from quart import current_app as app, request

async def ratelimit_handler():
    # dummy handler for future code
    print(request.headers)
