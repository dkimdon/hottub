# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Python library (`bwa/`) for communicating with Balboa Water Group spa/hot tub WiFi controllers over TCP port 4257.  This is a Python port of the Ruby `balboa_worldwide_app` gem.  It uses only Python standard library modules (Python 3.10+).

The live spa is at **10.0.0.105** (auto-discoverable via UDP broadcast to port 30303).

## Running Tests

```bash
# Unit tests — no hardware required, uses a simulated server
python3 -m unittest tests/test_crc.py tests/test_message.py -v

# Live integration tests — requires real spa on the local network
python3 -m unittest tests/test_live.py -v
```

`pytest` is not installed; use `python3 -m unittest`.  To run a single test:

```bash
python3 -m unittest tests.test_message.TestFrameRoundTrip.test_set_temperature -v
```

## Architecture

### `bwa/message.py` — framing and dispatch

`Message` is the base class.  Subclasses register themselves automatically via `__init_subclass__`, which populates `Message._registry` keyed by the 3-byte `MESSAGE_TYPE`.

- `Message.parse(frame: bytes) -> Message` — validates CRC, looks up subclass in registry, calls `_parse(payload)`
- `msg.to_bytes() -> bytes` — calls `_serialize_payload()` then wraps with length/CRC/delimiters
- `InvalidMessage(Exception)` — raised by `parse()` on any framing or CRC error; carries `.raw` bytes

Wire frame layout: `[0x7e][L][T0 T1 T2][payload...][CRC][0x7e]` where `L = len(payload) + 5` and CRC covers `[L T0 T1 T2 payload...]`.

### `bwa/messages/` — message types

Importing `bwa.messages` (or `bwa/messages/__init__.py`) registers all subclasses.  Every message type that is only received (never sent by the client) only implements `_parse()`; types that are sent implement `_serialize_payload()`.

`Status` (`ff af 13`, 24-byte payload) is the most important type — the spa broadcasts it ~once/second.  It is a `@dataclass` with fields for temperature, heating state, pumps, lights, etc.  Key payload byte indices: `[1]`=flags1/priming, `[2]`=current temp, `[3]`=hour, `[4]`=minute, `[5]`=heating mode, `[9]`=scale/24h, `[10]`=heating/range, `[11]`=pumps, `[13]`=circ pump, `[14]`=lights, `[20]`=set temp.  Celsius temperatures are halved after reading (`raw / 2.0`) and doubled before sending (`desired * 2`).

### `bwa/client.py` — TCP client

`Client(host, port=4257)` connects immediately on construction.  Key design points:

- `poll()` reads one frame, parses it, updates `last_status` / `last_filter_cycles` as a side effect
- `_read_frame()` accumulates bytes in `self._buf` and re-syncs on lost 0x7e alignment
- `set_temperature(desired)` doubles the value for Celsius (or when `desired < 50`, which also signals Celsius)
- `set_pump1/2(n)` computes how many toggles are needed from the current `last_status`; requires `poll_until_status()` to have been called first
- Context manager: `with Client(...) as spa:` closes the socket on exit

### `bwa/server.py` — simulated server (tests only)

Encodes `Status` objects to wire frames via the module-level `_encode_status_payload()` helper (not a method on `Status`, because `Status` is a `@dataclass` and doesn't inherit `Message.to_bytes()` normally).  Used by `tests/test_message.py` via `ServerThread` context manager.

### `bwa/discovery.py`

Sends UDP broadcast to `255.255.255.255:30303`, filters responses by MAC prefix `00-15-27`.  `find_spa()` returns the first IP found; `discover()` returns a `{ip: name}` dict.

## Key Conventions

- All message subclasses must set `MESSAGE_TYPE: ClassVar[bytes]` and `MESSAGE_LENGTH: ClassVar[int]` — these are checked by `Message.parse()`.
- `_parse(payload)` receives only the payload bytes (not the full frame).  Byte indices in `_parse` match the protocol doc directly.
- Temperature values stored in `Status` are always in display units (°F or °C as floats); the wire doubling is only applied in `_parse`/`_encode_status_payload` and `Client.set_temperature`.
- Live tests restore original tub state after each test.  Temperature tests use `_pick_alternate_temp()` to stay within the tub's current range (low: 50–80°F, high: 80–104°F).
