```
███╗   ███╗███████╗████████╗ █████╗     ███████╗ ██████╗██╗  ██╗███████╗██████╗ 
████╗ ████║██╔════╝╚══██╔══╝██╔══██╗    ██╔════╝██╔════╝██║  ██║██╔════╝██╔══██╗
██╔████╔██║█████╗     ██║   ███████║    ███████╗██║     ███████║█████╗  ██║  ██║
██║╚██╔╝██║██╔══╝     ██║   ██╔══██║    ╚════██║██║     ██╔══██║██╔══╝  ██║  ██║
██║ ╚═╝ ██║███████╗   ██║   ██║  ██║    ███████║╚██████╗██║  ██║███████╗██████╔╝
╚═╝     ╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝    ╚══════╝ ╚═════╝╚═╝  ╚═╝╚══════╝╚═════╝   
```

This project facilitates executing arbitrary batch jobs across multiple target systems in an HPC context.  
Besides Linux and Python version >= 3.9, the only[^1] requirement consists [rsync](https://rsync.samba.org/) (or [OpenSSH](https://www.openssh.com/) for `scp`) for transferring files to and from the target systems.
[^1]: [Full list of required software on the remote targets](docs/README.md#required-software-on-the-targets)

Please refer to the [administrator](./docs/README.md#administrators) and [user](./docs/README.md#users) documentation.

## To-Dos

- [ ] `mscli purge [-t <target> ...] -a` to delete `~/.meta-sched` from targets
- [ ] (Advanced) scheduling algorithms
- [ ] Energy reporting plugin
- [ ] Client-side re-scheduling