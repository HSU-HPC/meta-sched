# Meta-Scheduler

## To-Dos
- [ ] Job management
    - [x] Create (config)
    - [x] Submit
    - [x] List
    - [x] Cancel
- [x] Job spec examples
- [ ] Job attributes (cores, time, MPI etc.)
- [ ] Slurm support (partially done)
- [ ] PBS support
- [ ] (Green) scheduling algorithms
- [ ] Energy reporting (RAPL)
- [ ] API authentication (optional if only using localhost)
- [ ] Code documentation
- [ ] User documentation

## Requirements
- [uv](https://docs.astral.sh/uv/) as project/package manager
- [rsync](https://rsync.samba.org/) (or [OpenSSH](https://www.openssh.com/) for `scp`)

## Getting started
1. Set up the project using `./script/sync_project.sh`.
2. Build the installable Python package under `./dist/` using `./scripts/build_package.sh` or install it locally using `./scripts/install_package.sh`.
3. Start the meta-scheduler components using `ms-service --sudo`.
4. Submit job arrays using `ms-cli`.
