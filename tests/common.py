"""

Litecord
Copyright (C) 2018  Luna Mendes

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""

from .credentials import CREDS

async def login(acc_name: str, test_cli):
    creds = CREDS[acc_name]

    resp = await test_cli.post('/api/v6/auth/login', json={
        'email': creds['email'],
        'password': creds['password']
    })

    if resp.status_code != 200:
        raise RuntimeError(f'non-200 on login: {resp.status_code}')

    rjson = await resp.json
    return rjson['token']


async def get_uid(token, test_cli):
    resp = await test_cli.get('/api/v6/users/@me', headers={
        'Authorization': token
    })

    if resp.status_code != 200:
        raise RuntimeError(f'non-200 on get uid: {resp.status_code}')

    rjson = await resp.json
    return rjson['id']
