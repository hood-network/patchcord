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
# drop into the virtualenv's shell
$ pipenv shell

# boot litecord
$ hypercorn -b 0.0.0.0:5000 run:app
```
