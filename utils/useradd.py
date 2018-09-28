#!/usr/bin/env python3
import sys
import requests

def main():
    argv = sys.argv
    inst_url = 'https://discordapp.io'

    if len(argv) < 4:
        print('useradd.py <email> <username> <password>')
        return

    email, username, password = sys.argv[1:4]
    print('email', repr(email))
    print('username', repr(username))
    print('password', repr(password))
    resp = requests.post(f'{inst_url}/api/v6/auth/register', json={
        'email': email,
        'password': password,
        'username': username,
    }, headers={
        'Origin': inst_url
    })
    print(resp.status_code)
    print(resp.text)


if __name__ == '__main__':
    main()
