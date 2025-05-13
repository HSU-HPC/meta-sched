# Meta-Scheduler
This project facilitates executing arbitrary batch jobs across multiple target systems in an HPC context.  
Besides [Python 3.12](https://www.python.org/downloads/release/python-3120/) the only other requirement consists [rsync](https://rsync.samba.org/) (or [OpenSSH](https://www.openssh.com/) for `scp`) for transferring files to and from the target systems.

Please refer to the [documentation](./docs/README.md).

## To-Dos
- [ ] **FIXME:** Call MPI applications directly with sbatch -n <ranks> (Also fix MPI example)
- [ ] Job attributes (cores, time, MPI etc.)
- [ ] Slurm support (partially done)
- [ ] PBS support
- [ ] (Green) scheduling algorithms
- [ ] Energy reporting (RAPL)
- [ ] API authentication (optional if only using localhost)
- [ ] Split package into separate client/service packages
- [ ] [Documentation](./docs/README.md)
