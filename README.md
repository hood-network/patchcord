# litecord

Litecord is a free as in freedom implementation of Discord's backend services.

Rewrite of [litecord-reference].
[litecord-reference]: https://gitlab.com/lnmds/litecord-reference

## Install

- Python 3.6 or higher
- PostgreSQL

We use [pipenv] to manage our dependencies.
[pipenv]: https://github.com/pypa/pipenv

```
$ git clone https://gitlab.com/lnmds/litecord
$ cd litecord

# create users as you want, etc
$ psql -U some_user -f schema.sql database

# edit config.py as you please
$ cp config.example.py config.py

# install all packages, including dev-packages
$ pipenv install --dev
```

## Running

```
# hypercorn will by default bind to 0.0.0.0:5000, change that address
# with the -b option (e.g -b 0.0.0.0:6969).
# use '--access-log -' to show logs on stdout.
$ pipenv run hypercorn run:app
```
