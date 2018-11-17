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
