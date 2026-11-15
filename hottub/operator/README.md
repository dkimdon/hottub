# bwa — Balboa Worldwide App Python Library

Python library for communicating with Balboa Water Group spa/hot tub WiFi
controllers.  It implements the binary TCP protocol that runs over port 4257
and the UDP discovery protocol on port 30303.

Only Python standard library modules are used — no third-party packages are
required.

---

## Quick Start

```python
from bwa.client import Client
from bwa.discovery import find_spa

# Discover the spa's IP automatically
ip = find_spa()
print(f"Found spa at {ip}")

# Connect and read current status
with Client(ip) as spa:
    status = spa.poll_until_status()
    print(status)
    # <Status 10:30AM 102.0/104.0°F ready heating high>
```

---

## Installation

No installation required.  Add the `bwa/` directory to your Python path or
run your scripts from the `operator/` directory.

---

## Examples

### Read status

```python
from bwa.client import Client

with Client("10.0.0.105") as spa:
    status = spa.poll_until_status(timeout=5.0)
    if status is None:
        print("Tub unreachable")
    else:
        print(f"Current temp : {status.current_temperature}°F")
        print(f"Set point    : {status.set_temperature}°F")
        print(f"Heating      : {status.heating}")
        print(f"Heating mode : {status.heating_mode.value}")
        print(f"Pump 1       : {status.pump1}")   # 0=off, 1=low, 2=high
        print(f"Light 1      : {status.light1}")
        print(f"Time         : {status.format_time()}")
```

### Set temperature

```python
from bwa.client import Client

with Client("10.0.0.105") as spa:
    spa.poll_until_status()            # populate last_status first
    spa.set_temperature(104)           # Fahrenheit integer
    # For Celsius: spa.set_temperature(40)  (library doubles it automatically)
```

**Valid ranges:**
| Scale | Range | Min | Max |
|-------|-------|-----|-----|
| °F | high | 80 | 104 |
| °F | low  | 50 | 80  |
| °C | high | 26 | 40  |
| °C | low  | 10 | 26  |

The tub's current range is shown in `status.temperature_range`.

### Control pumps and lights

```python
from bwa.client import Client

with Client("10.0.0.105") as spa:
    spa.poll_until_status()

    # Toggle light
    spa.toggle_light1()

    # Set pump1 to a specific speed (0=off, 1=low, 2=high)
    # Uses the current status to calculate how many toggles are needed
    spa.set_pump1(2)

    # Set light to a specific state
    spa.set_light1(True)
```

### Discover spas on the network

```python
from bwa.discovery import discover, find_spa

# Return all spas: {ip: name}
spas = discover(timeout=5.0)
for ip, name in spas.items():
    print(f"{name} @ {ip}")

# Return just the first spa's IP
ip = find_spa()
```

### Continuous monitoring loop

```python
import time
from bwa.client import Client
from bwa.message import InvalidMessage

with Client("10.0.0.105") as spa:
    while True:
        try:
            msg = spa.poll()          # blocks until next message
            from bwa.messages.status import Status
            if isinstance(msg, Status):
                print(f"{msg.format_time()}  {msg.current_temperature}°F → {msg.set_temperature}°F")
        except InvalidMessage as e:
            print(f"Bad message: {e}")
        except KeyboardInterrupt:
            break
```

### Using the simulated server (for testing without hardware)

```python
import threading
from bwa.server import Server
from bwa.client import Client

port = 14257
srv = Server(port=port)
t = threading.Thread(target=srv.run, daemon=True)
t.start()

with Client("127.0.0.1", port) as spa:
    status = spa.poll_until_status()
    print(status)
    spa.set_temperature(103)

srv.stop()
```

---

## API Reference

### `bwa.client.Client`

```python
Client(host: str, port: int = 4257)
```

| Method | Description |
|--------|-------------|
| `poll() -> Message` | Block until one message arrives; update `last_status` if it's a Status |
| `poll_until_status(timeout=5.0) -> Status \| None` | Poll until Status or timeout |
| `messages_pending() -> bool` | True if data is waiting to be read |
| `drain()` | Discard all currently pending messages |
| `send(msg: Message)` | Send any message |
| `request_configuration()` | Ask the spa for hardware config |
| `request_filter_configuration()` | Ask for filter cycle schedule |
| `set_temperature(desired: float)` | Set target temperature (°F or °C) |
| `toggle_pump1() / toggle_pump2()` | Cycle pump speed 0→1→2→0 |
| `set_pump1(n) / set_pump2(n)` | Set pump to speed 0/1/2 via toggles |
| `toggle_light1()` | Toggle light on/off |
| `set_light1(on: bool)` | Set light to exact state |
| `toggle_heating_mode()` | Toggle between ready/rest |
| `toggle_temperature_range()` | Toggle between high/low range |
| `set_time(hour, minute, 24h=False)` | Set the spa's clock |
| `close()` | Close the TCP connection |

`Client` is also a context manager (`with Client(...) as spa:`).

Attributes:
- `last_status: Status | None` — most recently received Status message
- `last_filter_cycles: FilterCycles | None` — most recently received filter config

### `bwa.messages.status.Status`

Parsed from the spa's ~1Hz status broadcast.

| Attribute | Type | Description |
|-----------|------|-------------|
| `current_temperature` | `float \| None` | Actual water temp; `None` if unknown |
| `set_temperature` | `float` | Target temperature |
| `temperature_scale` | `TemperatureScale` | `.FAHRENHEIT` or `.CELSIUS` |
| `temperature_range` | `TemperatureRange` | `.HIGH` or `.LOW` |
| `heating_mode` | `HeatingMode` | `.READY`, `.REST`, `.READY_IN_REST` |
| `heating` | `bool` | True when heating element is active |
| `pump1`, `pump2` | `int` | Speed: 0=off, 1=low, 2=high |
| `light1` | `bool` | Light on/off |
| `circ_pump` | `bool` | Circulation pump running |
| `hour`, `minute` | `int` | Current time on the spa's clock |
| `twenty_four_hour_time` | `bool` | Display mode |
| `priming` | `bool` | True during startup warm-up |

### `bwa.discovery`

```python
discover(timeout=5.0, exhaustive=False) -> dict[str, str]  # {ip: name}
find_spa(timeout=5.0) -> str | None
```

### `bwa.message.Message`

Base class for all message types.  Subclasses:
`ConfigurationRequest`, `Configuration`, `ControlConfigurationRequest`,
`ControlConfiguration`, `ControlConfiguration2`, `FilterCycles`,
`SetTemperature`, `SetTemperatureScale`, `SetTime`, `ToggleItem`, `Status`.

```python
Message.parse(frame: bytes) -> Message   # parse a raw wire frame
msg.to_bytes() -> bytes                  # encode to wire frame
```

---

## Protocol Overview

The spa listens on **TCP port 4257**.  After connecting, it immediately begins
sending `Status` messages approximately once per second.

Each wire frame looks like:

```
[0x7e] [L] [T0 T1 T2] [payload ...] [CRC] [0x7e]
```

- `L` = `len(payload) + 5`
- `CRC` = CRC-8 (polynomial 0x07, initial 0x02, XOR out 0x02) over bytes `[L T0 T1 T2 payload...]`
- Total frame length = `L + 2`

Discovery uses a **UDP broadcast** to port 30303.  Balboa devices respond
with their hostname and MAC address; the MAC prefix `00-15-27` identifies
genuine Balboa hardware.

See `bwa/doc/protocol.md` (in the `balboa_worldwide_app` Ruby repo) for the
full wire-level specification.

---

## Running Tests

```bash
# Unit tests (no hardware required — uses a simulated server)
cd operator/
python3 -m unittest tests/test_crc.py tests/test_message.py -v

# Live integration tests (requires a real spa on the network)
python3 -m unittest tests/test_live.py -v
```

The live tests will auto-discover the spa via UDP.  If discovery is unreliable,
set `SPA_IP` at the top of `tests/test_live.py` to the known IP address.

The live tests make small changes (toggling lights, adjusting the set-point by
a degree or two) and restore everything to its original state afterwards.
