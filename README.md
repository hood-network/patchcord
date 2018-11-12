# litecord

Litecord is an open source implementation of Discord's backend and API in
Python.

This project is a rewrite of [litecord-reference].

[litecord-reference]: https://gitlab.com/luna/litecord-reference

## Notes

 - Unit testing isn't completly perfect.
 - No voice is planned to be developed, for now.
 - You must figure out connecting to the server yourself. Litecord will not distribute
    Discord's official client code nor provide ways to modify the client.

## Install

Requirements:
- Python 3.7 or higher
- PostgreSQL
- [Pipenv]

[pipenv]: https://github.com/pypa/pipenv

```sh
$ git clone https://gitlab.com/luna/litecord.git && cd litecord

# Setup the database:
# don't forget that you can create a specific
# postgres user just for the litecord database
$ createdb litecord
$ psql -f schema.sql litecord

# Configure litecord:
# edit config.py as you wish
$ cp config.example.py config.py

# run database migrations (this is a
# required step in setup)
$ pipenv run ./manage.py migrate

# Install all packages:
$ pipenv install --dev
```

## Running

Hypercorn is used to run litecord. By default, it will bind to `0.0.0.0:5000`.
You can use the `-b` option to change it (e.g. `-b 0.0.0.0:45000`).

Use `--access-log -` to output access logs to stdout.

```sh
$ pipenv run hypercorn run:app
```

## Updating

```sh
$ git pull
$ pipenv run ./manage.py migrate
```

## Running tests

To run tests we must create users that we know the passwords of.
Because of that, **never setup a testing environment in production.**

```sh
# setup the testing users
$ pipenv run ./manage.py setup_tests

# run tests
$ pipenv run tox
```
