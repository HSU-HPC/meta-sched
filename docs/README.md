# Meta-Scheduler Documentation

## Table of Contents

- :construction: [Installation](#installation)
- :construction_worker: [Administrators](#administrators)
- :computer: [Users](#users)

## Installation

1. Use [direnv](https://direnv.net/) or `source .envrc` to set up the project environment and set up [uv](https://docs.astral.sh/uv/), if it isn't already installed.
2. During development, use `mscli-dev` and `msserver-dev` to test the CLI and server respectively.
3. Build the installable Python package under `./src/<component>/dist/` using `package <all|client|server>`
4. Install the Python packages using `install <all|client|server>`. This also installs Python 3.12 (through [pyenv](https://github.com/pyenv/pyenv)) and [pipx](https://pipx.pypa.io/stable/).

## Administrators

After [installing the server package](#installation), execute it using:

```bash
MS_SERVER_HOST=localhost \
MS_SERVER_PORT=8001 \
MS_SCHED_CONFIG=config.toml \
msserver
```

While all environment variables are optional, the flag `--use-default-config` must be added to use the [default configuration file](../src/server/server/config/default.toml).  
If the application is running under a non-root user and requires `sudo`, add the flag `--sudo` to the command.

To persistently execute the server in the background after the system has booted, create a new [systemd unit](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html) or use a terminal multiplexer like [tmux](https://github.com/tmux/tmux/wiki) to manually run it in the background.

- `TODO customizing the configuration`

## Users

After [installing the client package](#installation), submit job arrays using `mscli`.

- `TODO usage of mscli`
- `TODO job files and spec`

