#!/usr/bin/env python3
import os
import pty
import fcntl
import termios
import struct
import pathlib
from collections import defaultdict
import asyncio
from aiohttp import web

async def handle_terminals_post(request):
    pid = 123
    print(f"pid: {pid}")
    return web.Response(body=str(pid), content_type='text/html')

async def handle_size_post(request, pid):
    size = 0
    print(f"size: {size}")
    return

def set_window_size(fd, col, row):
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", row, col, 0, 0))

async def read_stream(stream, resp):
    while True:
        data = await stream.read(1000)
        if data:
            # print(f"read: {data}")
            await resp.send_bytes(data)
        else:
            break

async def write_stream(stream, resp):
    async for msg in resp:
        if msg.type == web.WSMsgType.TEXT:
            data = msg.data.encode()
            # print(f"write: {data}")
            stream.write(data)
            await stream.drain()

async def wshandler(request):
    resp = web.WebSocketResponse()
    available = resp.can_prepare(request)
    if not available:
        # TODO: what should be done here?
        return

    print("connect")
    await resp.prepare(request)
    try:
        master, slave = pty.openpty()
        # TODO: setup handler to change dynamically w/ window size
        set_window_size(slave, 80, 26)
        p = await asyncio.create_subprocess_shell(
            'tmux', # 'bash -i',
            stdin=slave,
            stdout=slave,
            stderr=slave,
            bufsize=0)
        print(p.pid)
        request.app['sockets'][resp] = p

        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader()
        read_protocol = asyncio.StreamReaderProtocol(reader)
        read_transport, _ = await loop.connect_read_pipe(
            lambda: read_protocol, os.fdopen(master, 'rb'))
        write_protocol = asyncio.StreamReaderProtocol(asyncio.StreamReader())
        write_transport, _ = await loop.connect_write_pipe(
            lambda: write_protocol, os.fdopen(master, 'wb'))
        writer = asyncio.StreamWriter(write_transport, write_protocol, None, loop)

        await asyncio.gather(
            read_stream(reader, resp),
            write_stream(writer, resp))

        return resp

    finally:
        request.app['sockets'].pop(resp)
        print("disconnect")

async def on_shutdown(app):
    for ws in list(app['sockets'].keys()):
        await ws.close()

def init():
    app = web.Application()
    app['sockets'] = defaultdict(lambda: None)
    app.router.add_post('/terminals', handle_terminals_post)
    app.router.add_post('/terminals/{pid:.+}/size', handle_size_post)
    app.router.add_get('/terminals/{pid:.+}', wshandler)
    app.router.add_static('/', pathlib.Path(__file__).parent)
    app.on_shutdown.append(on_shutdown)
    return app

web.run_app(init())
