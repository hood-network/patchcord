# Operating a Litecord instance

`./manage.py` contains common admin tasks that you may want to do to the
instance, e.g make someone an admin, or migrate the database, etc.

Note, however, that many commands (example the ones related to user deletion)
may be moved to the Admin API without proper notice. There is no frontend yet
for the Admin API.

The possible actions on `./manage.py` can be accessed via `./manage.py -h`, or
`poetry run ./manage.py -h` if you're on poetry (recommended).

## `./manage.py generate_token`?

You can generate a user token but only if that user is a bot.

## Instance invites

If your instance has registrations disabled you can still get users to the
instance via instance invites. This is something only Litecord does, using a
separate API endpoint.

Use `./manage.py makeinv` to generate an instance invite, give it out to users,
point them towards `https://<your instance url>/invite_register.html`. Things
should be straightforward from there.

## Making someone Staff

**CAUTION:** Making someone staff, other than giving the Staff badge on their
user flags, also gives complete access over the Admin API. Only make staff the
people you (the instance OP) can trust.

Use the `./manage.py make_staff` management task to make someone staff. There is
no way to remove someone's staff with a `./manage.py` command _yet._
