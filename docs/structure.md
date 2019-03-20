# Project structure

## `attachments` and `images`

They're empty folders on purpose. Litecord will write files to them to hold
message attachments or avatars.

## `manage`

Contains the `manage.py` script's main function, plus all the commands.
A point of interest is the `manage/cmd/migration/scripts` folder, as they hold
all the SQL scripts required for migrations.

## `litecord`

The folder + `run.py` contain all of the backend's source code. The backend runs
Quart as its HTTP server, and a `websockets` server for the Gateway.

 - `litecord/blueprints` for everything HTTP related. 
 - `litecord/gateway` for main things related to the websocket or the Gateway.
 - `litecord/embed` contains code related to embed sanitization, schemas, and
    mediaproxy contact.
 - `litecord/ratelimits` hold the ratelimit implementation copied from
    discord.py plus a simple manager to hold the ratelimit objects. a point of
    interest is `litecord/ratelimits/handler.py` that holds the main thing.
 - `litecord/pubsub` is defined on `docs/pubsub.md`.
 - `litecord/voice` holds the voice implementation, LVSP client, etc.

There are other files around `litecord/`, e.g the snowflake library, presence/
image/job managers, etc.

## `static`

Holds static files, such as a basic index page and the `invite_register.html`
page.

## `tests`

Tests are run with `pytest` and the asyncio plugin for proper testing. A point
of interest is `tests/conftest.py` as it contains test-specific configuration
for the app object. Adding a test is trivial, as pytest will match against any
file containing `test_` as a prefix.
