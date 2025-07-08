```
███╗   ███╗███████╗████████╗ █████╗     ███████╗ ██████╗██╗  ██╗███████╗██████╗ 
████╗ ████║██╔════╝╚══██╔══╝██╔══██╗    ██╔════╝██╔════╝██║  ██║██╔════╝██╔══██╗
██╔████╔██║█████╗     ██║   ███████║    ███████╗██║     ███████║█████╗  ██║  ██║
██║╚██╔╝██║██╔══╝     ██║   ██╔══██║    ╚════██║██║     ██╔══██║██╔══╝  ██║  ██║
██║ ╚═╝ ██║███████╗   ██║   ██║  ██║    ███████║╚██████╗██║  ██║███████╗██████╔╝
╚═╝     ╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝    ╚══════╝ ╚═════╝╚═╝  ╚═╝╚══════╝╚═════╝   
```

This project facilitates executing arbitrary batch jobs across multiple target systems in an HPC context.  
Besides Linux and any Python3 version (for bootstrapping) the only other requirement consists [rsync](https://rsync.samba.org/) (or [OpenSSH](https://www.openssh.com/) for `scp`) for transferring files to and from the target systems.

Please refer to the [administrator](./docs/README.md#administrators) and [user](./docs/README.md#users) documentation.

## To-Dos
- [ ] (Green) scheduling algorithms
- [ ] Energy reporting (RAPL)
- [ ] [Documentation](./docs/README.md)
- [ ] Client side re-scheduling
- [ ] Use `flock /tmp/lockfile -c "..."` to "queue" tasks on a `DirectExecutionRemoteTarget` and `watch -n 1 "flock -n /tmp/lockfile -c ':' && echo 'free' || echo 'locked'"` to get the state of the target