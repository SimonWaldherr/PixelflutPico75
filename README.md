# Pixelflut Server for Raspberry Pi Pico (RP2040) with 128x128 LED Matrix

This project implements a Pixelflut server on a Raspberry Pi Pico (RP2040) with a 128x128 LED matrix using the Hub75 interface. It supports both traditional Pixelflut commands over TCP and modern HTTP requests for flexibility and easy integration with web clients. The project also includes a minimalistic web interface for setting pixels and viewing the current grid state in real-time.

## Features

- **TCP Pixelflut Mode**: Supports classic Pixelflut commands (`PX x y RRGGBB`) over TCP.
- **HTTP Mode**: Allows setting pixels using HTTP GET requests for easy integration with web clients.
- **Minimalistic Web Interface**: A simple HTML interface to interact with the LED matrix directly from a web browser.
- **WiFi/Access Point Setup**: Connect the Pico to an existing WiFi network or set it up as an Access Point (AP).

## Hardware Requirements

- Raspberry Pi Pico W (RP2040) - preferably the Pimoroni Interstate 75 W
- Hub75 compatible 128x128 LED matrix (configured with 512x32 modules)

## Software Requirements

- MicroPython firmware installed on the Raspberry Pi Pico

## Setup Instructions

1. **Flash MicroPython** on your Raspberry Pi Pico using [Thonny](https://thonny.org/) or another Python editor.
2. **Upload the server code** (`main.py`) to the Pico.
3. **Upload the HTML file** (`index.html`) to the Pico’s filesystem for the web interface.
4. **Configure WiFi credentials**:
   - Update the SSID and PASSWORD in the `main.py` file to match your WiFi network. Alternatively, the server can run in Access Point mode if no WiFi network is configured.

## Running the Server

1. Connect the Raspberry Pi Pico to power and open a serial console (e.g., via Thonny or another serial terminal).
2. The server will either connect to the specified WiFi network or start in AP mode (`pico_ap` with password `12345678`).
3. The IP address of the server will be printed in the console.
4. Access the server via your web browser at `http://<Pico_IP>:8080` to use the web interface.

## Using the Pixelflut Server

### TCP Pixelflut Mode

- The server listens for Pixelflut commands on TCP port `1234`.
- Example Pixelflut command: `PX 10 20 FF0000` (sets the pixel at coordinates `(10, 20)` to red).
- The server supports the following Pixelflut commands:
  - `PX <x> <y> <RRGGBB>`: Set pixel at `(x, y)` to the specified color.
  - `SIZE`: Get the size of the pixel grid.
  - `HELP`: Get help information about the Pixelflut commands.
  - `QUIT`: Close the connection.
- example (setting a pixel with netcat):
  ```
  $ echo -e "PX 10 20 FF0000\n" | nc <Pico_IP> 1234
  ```

### HTTP Mode

- The server listens on HTTP port `8080`.
- Set a pixel using a GET request:
  ```
  GET /px?x=<x>&y=<y>&color=<RRGGBB>
  ```
  Example:
  ```
  GET /px?x=10&y=20&color=FF0000
  ```

### Web Interface

- Open the `index.html` file in your browser:
  - You can click on the canvas to set pixels.
  
## Known Issues

- **Latency**: The Pico’s performance can vary based on the complexity of the HTTP requests and the number of clients.
- **WiFi Stability**: Ensure the WiFi module is connected properly. In case of issues, reboot the Pico and check connections.

## Future Improvements

- Implement **UDP support** for Pixelflut for faster pixel setting.
- Add **authentication** for the web interface and API endpoints for secure access.
- Improve **performance optimizations** for the server to handle more requests efficiently.

## Contributing

Feel free to submit pull requests or open issues if you encounter bugs or want to suggest improvements.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for more details.
