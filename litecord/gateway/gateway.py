import urllib.parse
from .websocket import GatewayWebsocket


async def websocket_handler(db, sm, ws, url):
    qs = urllib.parse.parse_qs(
        urllib.parse.urlparse(url).query
    )

    try:
        gw_version = qs['v'][0]
        gw_encoding = qs['encoding'][0]
    except (KeyError, IndexError):
        return await ws.close(1000, 'Invalid query args')

    if gw_version not in ('6',):
        return await ws.close(1000, 'Invalid gateway version')

    if gw_encoding not in ('json', 'etf'):
        return await ws.close(1000, 'Invalid gateway encoding')

    try:
        gw_compress = qs['compress'][0]
    except (KeyError, IndexError):
        gw_compress = None

    if gw_compress and gw_compress not in ('zlib-stream',):
        return await ws.close(1000, 'Invalid gateway compress')

    gws = GatewayWebsocket(sm, db, ws, v=gw_version,
                           encoding=gw_encoding, compress=gw_compress)
    await gws.run()
