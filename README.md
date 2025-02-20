# Meta-Scheduler

## To-Dos
- [ ] Job management
    - [ ] Create (config)
    - [x] Submit
    - [ ] List
    - [ ] Cancel
- [ ] Job attributes (cores, time, MPI etc.)
- [ ] Slurm support (partially done)
- [ ] PBS support
- [ ] (Green) scheduling algorithms
- [ ] Energy reporting (RAPL)
- [ ] API authentication (optional if only using localhost)
- [ ] Code documentation
- [ ] User documentation

## Getting started
This project uses [uv](https://docs.astral.sh/uv/) as a project/package manager.
1. Set up the project using `./script/sync_project.sh`.
2. Build the installable Python package under `./dist/` using `./scripts/build_package.sh` or install it locally using `./scripts/install_package.sh`.
3. Start the meta-scheduler components using `ms-service --sudo`.
4. Submit job arrays using `ms-cli`.
