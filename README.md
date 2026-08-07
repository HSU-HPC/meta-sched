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

## Citation

If you use the Meta Scheduler in scientific work, please cite:

```bibtex
@inproceedings{Horn2026,
  title           = "Pooling {HPC} Resources Across Organizations and Reducing
                     Carbon Emissions with Transparent, User-Centric
                     Meta-Scheduling",
  booktitle       = "2026 25th International Symposium on Parallel and
                     Distributed Computing ({ISPDC})",
  author          = "Horn, Ruben and Pla{\ss}, Marco and Neumann, Philipp",
  publisher       = "IEEE",
  pages           = "20--29",
  month           =  jul,
  year            =  2026,
  DOI             = "10.1109/ispdc69862.2026.00012",
  location        = "Hamburg, Germany"
}
```
