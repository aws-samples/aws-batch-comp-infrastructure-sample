# Install software dependencies

You must install several software packages and command-line tools
in order to use our project.
Install them in the following order.

1. [Python](#python)
2. [Docker](#docker)
3. [Node.js](#node)
4. [`aws`](#the-aws-command-line-tool) (AWS command-line-tool)
5. [`cdk`](#the-cdk-command-line-tool) (synthesizes AWS commands for infrastructure-as-code)


## Python

You need `python3` version 3.12 or higher.
Install the latest version for your platform
[here](https://www.python.org/downloads/).

If you use a development environment management tool
such as [`mise`](https://mise.jdx.dev/),
you might be able to install/switch Python versions with the tool
instead of downloading the source code from Python's website:
```bash
mise use python@3.12
```

Once you have Python installed,
you can verify which version you have by running:
```bash
python3 --version    # Should be at least v3.12
```

Then install this project's Python package dependencies 
with the `satcomp-activate.sh` script.
The script installs the dependencies into a
[virtual environment](https://docs.python.org/3/library/venv.html),
placed at the project's root
in `.venv/`.
The list of Python dependencies can be found at
`/requirements.txt`.

The `satcomp-activate.sh` script also sets `$PYTHONPATH` and `$SATCOMP_ROOT` and activates the virtual environment. You should source this file before using this project.
```bash
source satcomp-activate.sh
```

Note that `satcomp-activate.sh` will also check the dependencies below, and will warn if any are not satisfied.

## Docker

Download Docker Desktop for your platform
[here](https://www.docker.com/).

Docker Desktop comes with the `docker` command-line tool,
which this project uses to build and manage your solver images and containers.
You need version at least 25.0.
You can verify which version you have by running:
```bash
docker --version    # Should be at least v25.0
```
At this point,
Docker might complain that it isn't running.
To start the daemon,
open the Docker Desktop application.
You might have to do this each time you restart your machine.
(You can adjust this setting in the GUI:
Go to "Settings,"
perhaps by clicking the cog wheel in the top-right of the GUI,
and check the box "Start Docker Desktop when you sign in to your computer,"
found under "General" settings.
Don't forget to click "Apply" at the bottom-right when you're done.)

If you're SSH'ing into a remote machine without a GUI,
you might be able to install `docker`
through a package manager
such as `apt` or `yum`.
A common package name is `docker.x86_64`.
If that doesn't work,
you may have to install
[Docker Engine](https://docs.docker.com/engine/install/)
instead.


## Node.js

You need `node` version 22.0 or higher,
as well as the Node Package Manager `npm`.
We recommend that you use a Node version manager,
such as
[`nvm`](https://github.com/nvm-sh/nvm?tab=readme-ov-file#installing-and-updating)
or
[`nodist`](https://github.com/nodists/nodist),
to handle installation for you
(although you are free to manually install the latest version for your platform
[here](https://docs.npmjs.com/downloading-and-installing-node-js-and-npm)).
Using a Node version manager is particularly important
if your machine already has a version of `node` installed,
or if you need to switch between different `node` versions for different projects.

For example,
if you use `nvm`,
then you can run:
```bash
nvm install 24.2.0
nvm alias default 24.2.0    # Optionally make this version the system default
nvm use 24.2.0

node --version    # Should be at least v22.0
npm --version
```

If your machine is some version of an
[Amazon cloud desktop](https://docs.aws.amazon.com/workspaces/latest/adminguide/amazon-workspaces.html),
then you can use the package manager
[`mise`](https://github.com/jdx/mise)
(assuming it is already installed;
if not, install it
[here](https://mise.jdx.dev/installing-mise.html)).
You can run:
```bash
mise use node@22 npm@11
mise use -g node@22 npm@11    # Use these versions as the default option
```


## The `aws` command-line tool

The
[`aws` command-line tool](https://aws.amazon.com/cli/)
manages your AWS account credentials
and allows you to request and release AWS resources
from your machine.
Install it
[here](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html).

We don't require any particular version
(the latest version as of July 2025 should do).
Confirm you have the tool installed by running:
```bash
aws help
```

## The `cdk` command-line tool

Amazon's [Cloud Development Kit](https://aws.amazon.com/cdk/)
(CDK)
manages groups of AWS resources,
called *stacks*,
on your behalf.
You can install it with the Node Package Manager
(which you installed above).
Read more about how to install `cdk`
[here](https://docs.aws.amazon.com/cdk/v2/guide/getting-started.html).
```bash
npm install -g aws-cdk
cdk --version    # Should be at least v2.0
```
If you run into a permission error,
you might want to install it with `sudo` instead:
```bash
sudo npm install -g aws-cdk
``` -->

## Wrapping up

Run `satcomp-activate.sh` again to confirm that all dependencies are now satisfied.
