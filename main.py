import network
import socket
import gc
import hub75
import machine
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
UDP_PORT = 1235  # Port for UDP Pixelflut
AUTH_TOKEN = "changeme"
BUFFER_SIZE = 512
GC_INTERVAL = 50

# Initialize the display with the actual hardware resolution
xHEIGHT = 32    # Height of the physical LED matrix
xWIDTH = 512    # Width of the physical LED matrix
display = hub75.Hub75(xWIDTH, xHEIGHT)

# Create a 128x128 grid to store pixel states
grid = [[(0, 0, 0) for _ in range(WIDTH)] for _ in range(HEIGHT)]
request_count = 0

try:
    with open("auth_token.txt", "r") as token_file:
        AUTH_TOKEN = token_file.read().strip() or AUTH_TOKEN
except OSError:
    pass

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
    if not (0 <= x < WIDTH and 0 <= y < HEIGHT):
        return
    if grid[y][x] == (r, g, b):
        return
    x1, y1 = remap_pixel(x, y)
    if 0 <= x1 < xWIDTH and 0 <= y1 < xHEIGHT:
        display.set_pixel(x1, y1, r, g, b)
    grid[y][x] = (r, g, b)

def maybe_gc_collect():
    global request_count
    request_count += 1
    if request_count >= GC_INTERVAL:
        gc.collect()
        request_count = 0

def auth_tokens_match(expected, actual):
    if not expected or not actual or len(expected) != len(actual):
        return False
    diff = 0
    for i in range(len(expected)):
        diff |= ord(expected[i]) ^ ord(actual[i])
    return diff == 0

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

def get_request_path(data):
    try:
        if isinstance(data, bytes):
            data = data.decode()
        return data.split("\r\n", 1)[0].split(" ")[1]
    except (IndexError, UnicodeError):
        return "/"

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
        data = await reader.read(BUFFER_SIZE)
        if not data:
            return

        response = parse_pixelflut_command(data)
        writer.write(response)
        await writer.drain()
        writer.close()
        await writer.wait_closed()
        maybe_gc_collect()
    except Exception as e:
        print('TCP client error:', e)

async def tcp_pixelflut_server():
    print('TCP Pixelflut server listening on port', TCP_PORT)
    server = await asyncio.start_server(handle_tcp_client, "0.0.0.0", TCP_PORT)

    async with server:
        #await server.serve_forever()
        # AttributeError: 'Server' object has no attribute 'serve_forever'
        await asyncio.sleep(3600)

async def udp_pixelflut_server():
    print('UDP Pixelflut server listening on port', UDP_PORT)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    sock.bind(("0.0.0.0", UDP_PORT))
    while True:
        try:
            data, addr = sock.recvfrom(BUFFER_SIZE)
            response = parse_pixelflut_command(data)
            if response and response != b'OK':
                sock.sendto(response, addr)
            maybe_gc_collect()
        except OSError:
            await asyncio.sleep_ms(5)

def extract_auth_token(data):
    try:
        request_text = data.decode()
        request = request_text.split("\r\n")
        path = get_request_path(request_text)
        if "?auth=" in path:
            return path.split("?auth=")[1].split("&")[0]
        if "&auth=" in path:
            return path.split("&auth=")[1].split("&")[0]
        for header in request[1:]:
            if header.startswith("Authorization: Bearer "):
                return header.split("Authorization: Bearer ", 1)[1].strip()
    except (IndexError, UnicodeError):
        pass
    return None

async def handle_http_client(reader, writer):
    try:
        data = await reader.read(BUFFER_SIZE)
        if not data:
            return

        if not auth_tokens_match(AUTH_TOKEN, extract_auth_token(data)):
            writer.write(b'HTTP/1.1 401 Unauthorized\r\nWWW-Authenticate: Bearer realm="pixelflut"\r\nContent-Type: text/plain\r\n\r\nUnauthorized')
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            return

        path = get_request_path(data)
        if path == "/" or path.startswith("/?"):
            with open('index.html', 'r') as f:
                html = f.read()
            response = b'HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n' + html.encode()
            writer.write(response)
        elif not path.startswith("/px?"):
            writer.write(b'HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\n\r\nNot Found')
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
        maybe_gc_collect()
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
    await asyncio.gather(tcp_pixelflut_server(), udp_pixelflut_server(), http_pixelflut_server(ip))

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Server stopped manually.")
    finally:
        display.stop()
        print("Server stopped.")
