import network
import socket
import gc
import hub75
from machine import Pin
import time
import micropython
import json
import uasyncio as asyncio

# overclocking if necessary 
if machine.freq() != 240000000:
    machine.freq(240000000)

# Constants for the physical display
HEIGHT = 128
WIDTH = 128
HTTP_PORT = 8080  # Port for HTTP
TCP_PORT = 1234  # Port for Pixelflut

# Initialize the display with the actual hardware resolution
xHEIGHT = 32    # Height of the physical LED matrix
xWIDTH = 512    # Width of the physical LED matrix
display = hub75.Hub75(xWIDTH, xHEIGHT)

# Create a 128x128 grid to store pixel states
grid = [[(0, 0, 0) for _ in range(WIDTH)] for _ in range(HEIGHT)]

@micropython.native
def remap_pixel(x, y):
    """Remap (x, y) coordinates from the logical 128x128 grid to the physical LED matrix."""
    yh = y % 64
    if y < 64:
        if x < 32:
            return 192 + yh, 31 - x
        elif x < 64:
            return 191 - yh, x - 32
        elif x < 96:
            return 64 + yh, 31 - (x - 64)
        elif x < 128:
            return 63 - yh, x - 96
    elif y < 128:
        if x < 32:
            return 256 + yh, 31 - x
        elif x < 64:
            return 383 - yh, x - 32
        elif x < 96:
            return 384 + yh, 31 - (x - 64)
        elif x < 128:
            return 511 - yh, x - 96
    else:
        return x, y

@micropython.native
def draw_pixel(x, y, r, g, b):
    """Draw a pixel on the LED matrix at the given coordinates with mapping applied."""
    x1, y1 = remap_pixel(x, y)
    if 0 <= x1 < xWIDTH and 0 <= y1 < xHEIGHT:
        display.set_pixel(x1, y1, r, g, b)
    grid[y][x] = (r, g, b)

def parse_http_pixel_data(data):
    """
    Parse HTTP requests for pixel data in the format:
    GET /px?x=<x>&y=<y>&color=<RRGGBB>
    """
    try:
        if b"GET /px?" in data:
            params = data.split(b" ")[1].split(b"?")[1].split(b"&")
            x = int([param.split(b"=")[1] for param in params if param.startswith(b"x=")][0])
            y = int([param.split(b"=")[1] for param in params if param.startswith(b"y=")][0])
            color = [param.split(b"=")[1] for param in params if param.startswith(b"color=")][0]
            r = int(color[0:2], 16)
            g = int(color[2:4], 16)
            b = int(color[4:6], 16)
            return x, y, r, g, b
        return None
    except (IndexError, ValueError):
        return None

def parse_pixelflut_command(data):
    try:
        command = data.decode().strip()
        if command.startswith("PX"):
            _, x, y, color = command.split(" ")
            x, y = int(x), int(y)
            r, g, b = int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)
            draw_pixel(x, y, r, g, b)
            return b'OK'
        elif command == "SIZE":
            return f'{WIDTH} {HEIGHT}'.encode()
        elif command == "RESET":
            for y in range(HEIGHT):
                for x in range(WIDTH):
                    draw_pixel(x, y, 0, 0, 0)
            return b'OK'
        else:
            return b'Invalid command'
    except (ValueError, IndexError):
        return b'Invalid command'

async def handle_tcp_client(reader, writer):
    try:
        data = await reader.read(512)
        if not data:
            return

        response = parse_pixelflut_command(data)
        writer.write(response)
        await writer.drain()
        writer.close()
        await writer.wait_closed()
        gc.collect()
    except Exception as e:
        print('TCP client error:', e)

async def tcp_pixelflut_server():
    print('TCP Pixelflut server listening on port', TCP_PORT)
    server = await asyncio.start_server(handle_tcp_client, "0.0.0.0", TCP_PORT)

    async with server:
        #await server.serve_forever()
        # AttributeError: 'Server' object has no attribute 'serve_forever'
        await asyncio.sleep(3600)

async def handle_http_client(reader, writer):
    try:
        data = await reader.read(512)
        if not data:
            return

        if b"GET /" in data and not b"GET /px" in data:
            with open('index.html', 'r') as f:
                html = f.read()
            response = b'HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n' + html.encode()
            writer.write(response)
        else:
            pixel_data = parse_http_pixel_data(data)
            if pixel_data:
                x, y, r, g, b = pixel_data
                draw_pixel(x, y, r, g, b)
                response = b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nPixel set'
            else:
                response = b'HTTP/1.1 400 Bad Request\r\nContent-Type: text/plain\r\n\r\nInvalid pixel data'
            writer.write(response)

        await writer.drain()
        writer.close()
        await writer.wait_closed()
        gc.collect()
    except Exception as e:
        print('HTTP client error:', e)

async def http_pixelflut_server(ip):
    print('HTTP Pixelflut server listening on port', HTTP_PORT)
    server = await asyncio.start_server(handle_http_client, ip, HTTP_PORT)

    async with server:
        #await server.serve_forever()
        # AttributeError: 'Server' object has no attribute 'serve_forever'
        await asyncio.sleep(3600)

def setup_access_point(ssid, password):
    ap = network.WLAN(network.AP_IF)
    ap.config(essid=ssid, password=password)
    ap.active(True)
    while not ap.active():
        time.sleep(1)
    return ap.ifconfig()[0]

def setup_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid, password)
    max_wait = 10
    while max_wait > 0:
        if wlan.status() < 0 or wlan.status() >= 3:
            break
        max_wait -= 1
        print('waiting for connection...')
        time.sleep(1)
    return wlan.status() == 3

async def main():
    # Setup network and start the server
    if not setup_wifi('SSID', 'PASSWORD'):
        ip = setup_access_point('pico_ap', '12345678')
        print('Access point started at', ip)
    else:
        wlan = network.WLAN(network.STA_IF)
        ip = wlan.ifconfig()[0]
        print('Connected to WiFi at', ip)

    display.start()

    # Start both servers concurrently
    await asyncio.gather(tcp_pixelflut_server(), http_pixelflut_server(ip))

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Server stopped manually.")
    finally:
        display.stop()
        print("Server stopped.")
