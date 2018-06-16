litecord
============

Rewrite of [litecord-reference](https://gitlab.com/lnmds/litecord-reference).

Litecord is a free as in freedom implementation of Discord's backend services.

## Install

 - Python 3.6+
 - PostgreSQL

```
git clone https://gitlab.com/lnmds/litecord
cd litecord
python3.6 -m pip install -Ur requirements.txt
```

## Run

```
hypercorn run:app
```
