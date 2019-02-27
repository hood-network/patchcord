![Litecord logo](static/logo/logo.png)

Litecord is an open source, [clean-room design][clean-room] reimplementation of
Discord's HTTP API and Gateway in Python 3.

This project is a rewrite of [litecord-reference] and [litecord serviced].

[clean-room]: https://en.wikipedia.org/wiki/Clean_room_design
[litecord-reference]: https://gitlab.com/luna/litecord-reference
[litecord serviced]: https://github.com/litecord

## Wait, two other Litecords?

The first version is litecord-reference, written in Python and used MongoDB
as storage. It was rewritten into "litecord serviced" so that other developers
could help writing it, defining a clear protocol between components
(litebridge). Sadly, it didn't take off, so I (Luna), that wrote the other two,
took a shot at writing it again. It works.

**This is "Litecord" / "litecord".** There are *no* rewrites planned.

## Project Goals

- Being able to unit test bots in an autonomous fashion.
- Doing research and exploration on the Discord API.

### Non-goals

- Being used as a "self-hostable Discord alternative".

## Caveats

- Unit testing is incomplete.
- Currently, there are no plans to support voice chat, or the Discord Store.
- You must figure out how to connect to a Litecord instance. Litecord will not
  distribute official client code from Discord nor provide ways to modify the
  official client.

## Implementation status, AKA "Does it work?"

Approximately 80% of the REST API is reimplemented in Litecord. A wild guess
for the Gateway / Websockets API is 95%. Reminder that those do not count voice
specific components, but do count things the official client uses, such as
[lazy guilds](https://luna.gitlab.io/discord-unofficial-docs/lazy_guilds.html).

Tracking routes such as `/api/science` have dummy implementations so they don't
crash the client. They do not store any information given by the client.

Also consider that reimplementing the Discord API is kind-of a moving target, as
Discord can implement parts of the API that aren't documented at any point in
time.

## Liability

We (Litecord and contributors) are not liable for usage of this software,
valid or invalid. If you intend to use this software as a "self-hostable
Discord alternative", you are soely responsible for any legal action delivered
by Discord if you are using their assets, intellectual property, etc.

All referenced material for implementation is based off of
[official Discord API documentation](https://discordapp.com/developers/docs)
or third party libraries (such as [Eris](https://github.com/abalabahaha/eris)).

## Installation

Requirements:

- **Python 3.7+**
- PostgreSQL (tested using 9.6+)
- gifsicle for GIF emoji and avatar handling
- [pipenv]

[pipenv]: https://github.com/pypa/pipenv

### Download the code

```sh
$ git clone https://gitlab.com/litecord/litecord.git && cd litecord
```

### Install packages

```sh
$ pipenv install --dev
```

### Setting up the database

It's recommended to create a separate user for the `litecord` database.

```sh
# Create the PostgreSQL database.
$ createdb litecord

# Apply the base schema to the database.
$ psql -f schema.sql litecord
```

Copy the `config.example.py` file and edit it to configure your instance (
postgres credentials, etc):

```sh
$ cp config.example.py config.py
$ $EDITOR config.py
```

Then, you should run database migrations:

```sh
$ pipenv run ./manage.py migrate
```

## Running

Hypercorn is used to run Litecord. By default, it will bind to `0.0.0.0:5000`.
This will expose your Litecord instance to the world. You can use the `-b`
option to change it (e.g. `-b 0.0.0.0:45000`).

```sh
$ pipenv run hypercorn run:app
```

You can use `--access-log -` to output access logs to stdout.

**It is recommended to run litecord behind [NGINX].** You can use the
`nginx.conf` file at the root of the repository as a template.

[nginx]: https://www.nginx.com

### Does it work?

You can check if your instance is running by performing an HTTP `GET` request on
the `/api/v6/gateway` endpoint. For basic websocket testing, a tool such as
[ws](https://github.com/hashrocket/ws) can be used.

## Updating

Update the code and run any new database migrations:

```sh
$ git pull
$ pipenv run ./manage.py migrate
```

## Running tests

Running tests involves creating dummy users with known passwords. Because of
this, you should never setup a testing environment in production.

```sh
# Setup any testing users:
$ pipenv run ./manage.py setup_tests

# Install tox:
$ pip install tox

# Run lints and tests:
$ tox
```
