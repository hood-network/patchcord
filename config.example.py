MODE = 'Development'


class Config:
    HOST = 'localhost'
    PORT = 8081
    POSTGRES = {}


class Development(Config):
    DEBUG = True
    POSTGRES = {
        'host': 'localhost',
        'user': 'litecord',
        'password': '123',
        'database': 'litecord',
    }


class Production(Config):
    pass
