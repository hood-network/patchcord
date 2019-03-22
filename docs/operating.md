# Operating a Litecord instance

`./manage.py` contains common admin tasks that you may want to do to the
instance, e.g make someone an admin, or migrate the database, etc.

Note, however, that many commands (example the ones related to user deletion)
may be moved to the Admin API without proper notice. There is no frontend yet
for the Admin API.

The possible actions on `./manage.py` can be accessed via `./manage.py -h`, or
`pipenv run ./manage.py -h` if you're on pipenv.

## `./manage.py generate_token`?

You can generate a user token but only if that user is a bot.
