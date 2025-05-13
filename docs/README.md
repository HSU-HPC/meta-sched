# Meta-Scheduler Documentation

## Table of Contents

- :construction: [Installation](#installation)
- :construction_worker: [Administrators](#administrators)
- :computer: [Users](#users)

## Installation

:exclamation: Users may skip this section if `which ms-cli` returns a path to the installed CLI.

1. Make sure [uv](https://docs.astral.sh/uv/) (project/package manager) is installed
2. Set up the project using `./script/sync_project.sh`.
3. Build the installable Python package under `./dist/` using `./scripts/build_package.sh` or install it locally using `./scripts/install_package.sh`.
4. Start the meta-scheduler components using `ms-service --sudo`.

- `TODO installing the application for users`

## Administrators

After [installating the application](#installation), the service can be executed using:

```bash
MS_SERVICE_HOST=localhost \
MS_SERVICE_PORT=8001 \
MS_SCHED_CONFIG=config.toml \
ms-service
```

While all environment variables are optional, the flag `--use-default` must be added to use the [default configuration file](../meta_sched/data/examples/config.toml).  
If the application is running under a non-root user and requires `sudo`, add the flag `--sudo` to the command.

To persistently execute the service in the background after the system has booted, create a new [systemd unit](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html) or use a terminal multiplexer like [tmux](https://github.com/tmux/tmux/wiki) to manually run it in the background.

- `TODO customizing the configuration`

## Users

Submit job arrays using `ms-cli`.

- `TODO usage of ms-cli`
- `TODO job files and spec`

