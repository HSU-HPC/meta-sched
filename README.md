```
███╗   ███╗███████╗████████╗ █████╗     ███████╗ ██████╗██╗  ██╗███████╗██████╗ 
████╗ ████║██╔════╝╚══██╔══╝██╔══██╗    ██╔════╝██╔════╝██║  ██║██╔════╝██╔══██╗
██╔████╔██║█████╗     ██║   ███████║    ███████╗██║     ███████║█████╗  ██║  ██║
██║╚██╔╝██║██╔══╝     ██║   ██╔══██║    ╚════██║██║     ██╔══██║██╔══╝  ██║  ██║
██║ ╚═╝ ██║███████╗   ██║   ██║  ██║    ███████║╚██████╗██║  ██║███████╗██████╔╝
╚═╝     ╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝    ╚══════╝ ╚═════╝╚═╝  ╚═╝╚══════╝╚═════╝   
```

This project facilitates executing arbitrary batch jobs across multiple target systems in an HPC context.  
Besides Linux and [Python 3.12](https://www.python.org/downloads/release/python-3120/) the only other requirement consists [rsync](https://rsync.samba.org/) (or [OpenSSH](https://www.openssh.com/) for `scp`) for transferring files to and from the target systems.

Please refer to the [administrator](./docs/README.md#administrators) and [user](./docs/README.md#users) documentation.

## To-Dos
- [ ] (Green) scheduling algorithms
- [ ] Energy reporting (RAPL)
- [ ] API authentication (optional if only using localhost)
- [ ] [Documentation](./docs/README.md)
- [ ] Refactor class Target into two non-common classes
- [ ] Refactor job execution in target classes (Single function with concrete implementation of sub-steps like "await_job_end(...)")
- [ ] Add type checking where necessary
- [ ] Add local task queue for direct targets?
