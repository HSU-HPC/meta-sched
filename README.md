# Meta-Scheduler
This project facilitates executing arbitrary batch jobs across multiple target systems in an HPC context.  
Root access is **not** required for target systems and local SSH credentials of the users is used.   
_TODO: Insert diagram_

## To-Dos
- [ ] **FIXME:** Call MPI applications directly with sbatch -n <ranks> (Also fix MPI example)
- [ ] Job attributes (cores, time, MPI etc.)
- [ ] Slurm support (partially done)
- [ ] PBS support
- [ ] (Green) scheduling algorithms
- [ ] Energy reporting (RAPL)
- [ ] API authentication (optional if only using localhost)
- [ ] User documentation
- [ ] Refactoring: Daemon-less client using disowned process ignoring SIGHUP

## Requirements
- [uv](https://docs.astral.sh/uv/) as project/package manager
- [rsync](https://rsync.samba.org/) (or [OpenSSH](https://www.openssh.com/) for `scp`)

## Getting started
1. Set up the project using `./script/sync_project.sh`.
2. Build the installable Python package under `./dist/` using `./scripts/build_package.sh` or install it locally using `./scripts/install_package.sh`.
3. Start the meta-scheduler components using `ms-service --sudo`.
4. Submit job arrays using `ms-cli`.
