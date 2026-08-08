# my_gleam_webserver

A small Gleam/Cowboy HTTP server that runs under OTP application supervision.

## Run the server

Use the launcher for development and production entrypoints on Unix-like systems:

```sh
bash bin/graceful-beam-launcher gleam run
```

`SHUTDOWN_GRACE_MS` controls the bounded drain period and defaults to 30,000 ms.

The shutdown policy is:

- `SIGTERM` starts OTP's orderly application shutdown immediately. One signal is sufficient.
- A first interactive `SIGINT` starts the same graceful shutdown and logs that force shutdown is available.
- While draining after an interactive `SIGINT`, a second `SIGINT` or terminal EOF (`Ctrl-D` on an empty line) force-stops the BEAM process group.
- When stdin is not a TTY, one `SIGINT` or `SIGTERM` is sufficient; the grace deadline remains the automatic force fallback.
- The OTP application callback logs application drain and completion while the launcher logs signal, TTY, deadline, and force transitions.

The launcher is intentionally outside the BEAM VM because OTP handles `SIGTERM` as an orderly VM stop but does not expose terminal `SIGINT` through the normal Erlang signal-subscription API.

## Development

```sh
gleam deps download
gleam test
gleam format --check src test
bash -n bin/graceful-beam-launcher
python3 test/graceful_beam_launcher_test.py
```
