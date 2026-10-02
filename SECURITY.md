# Security

Please report security problems privately through
[GitHub's private vulnerability reporting](https://github.com/Abtektas/px4-ca-lint/security/advisories/new),
not in a public issue.

The tool reads parameter files and runs a local program on them. It does not
connect to a vehicle or to the network. A parameter file that makes the tool or
the engine crash, hang or write outside its temporary directory is a security
problem worth reporting.

A wrong or missing finding is not a security problem. Please open a normal
issue for it.

Only the latest release is supported.
