#!/bin/bash

# Get the full absolute path to the project root
# (i.e., the directory containing this script)
# Use BASH_SOURCE[0] instead of $0 because this script is sourced, not executed
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check dependencies (see docs/reference/software-requirements.md)
# Python 3.12+ is required; all others are warnings.
_warn() { echo "WARNING: $1"; }

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
if [ -z "$PYTHON_VERSION" ]; then
  echo "ERROR: python3 not found. Please install Python 3.12 or later."
  return 1 2>/dev/null || exit 1
elif [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 12 ]; }; then
  echo "ERROR: Python 3.12+ required, but found Python $PYTHON_VERSION"
  return 1 2>/dev/null || exit 1
fi

# Docker 25.0+
DOCKER_VERSION=$(docker --version 2>/dev/null | grep -oP '\d+\.\d+' | head -1)
if [ -z "$DOCKER_VERSION" ]; then
  _warn "docker not found. Install Docker 25.0+ (https://www.docker.com/)"
elif [ "$(echo "$DOCKER_VERSION" | cut -d. -f1)" -lt 25 ]; then
  _warn "Docker 25.0+ required, but found Docker $DOCKER_VERSION"
fi

# Node.js 22.0+
NODE_VERSION=$(node --version 2>/dev/null | grep -oP '\d+' | head -1)
if [ -z "$NODE_VERSION" ]; then
  _warn "node not found. Install Node.js 22+ (https://nodejs.org/)"
elif [ "$NODE_VERSION" -lt 22 ]; then
  _warn "Node.js 22+ required, but found Node $(node --version 2>/dev/null)"
fi

# AWS CLI
if ! command -v aws &>/dev/null; then
  _warn "aws CLI not found. Install it (https://aws.amazon.com/cli/)"
fi

# CDK 2.0+
CDK_MAJOR=$(cdk --version 2>/dev/null | grep -oP '^\d+' | head -1)
if [ -z "$CDK_MAJOR" ]; then
  _warn "cdk not found. Install it: npm install -g aws-cdk"
elif [ "$CDK_MAJOR" -lt 2 ]; then
  _warn "CDK 2.0+ required, but found CDK $(cdk --version 2>/dev/null)"
fi

unset -f _warn

if [ ! -d "$SCRIPT_DIR/.venv" ]; then
  echo ".venv directory didn't exist at project source, creating now..."

  echo "% python3 -m venv --prompt venv-satcomp $SCRIPT_DIR/.venv"
  python3 -m venv --prompt venv-satcomp $SCRIPT_DIR/.venv

  echo "% source $SCRIPT_DIR/.venv/bin/activate"
  source $SCRIPT_DIR/.venv/bin/activate

  echo "% python3 -m pip install -r $SCRIPT_DIR/requirements.txt"
  python3 -m pip install -r $SCRIPT_DIR/requirements.txt
else
  echo "% source $SCRIPT_DIR/.venv/bin/activate"
  source $SCRIPT_DIR/.venv/bin/activate
fi

# Add satcomp.py to PATH so it can be run from anywhere
# Use word boundaries to avoid matching subdirectories like .venv/bin
if [[ ! ":$PATH:" =~ ":$SCRIPT_DIR:" ]]; then
  echo "% export PATH=\"\$PATH:$SCRIPT_DIR\""
  export PATH="$PATH:$SCRIPT_DIR"
fi

# Set SATCOMP_ROOT for use in config files
# Configs can use $SATCOMP_ROOT/examples/... instead of relative paths
if [ -z "${SATCOMP_ROOT+x}" ] || [ "$SATCOMP_ROOT" != "$SCRIPT_DIR" ]; then
  echo "% export SATCOMP_ROOT=$SCRIPT_DIR"
  export SATCOMP_ROOT=$SCRIPT_DIR
fi

# Add the scripting/ directory to PYTHONPATH
PY_SCRIPTING_DIR=$SCRIPT_DIR/scripting
if [ -z ${PYTHONPATH+x} ]; then
  PYTHONPATH=""
fi

if [[ ! $PYTHONPATH =~ $PY_SCRIPTING_DIR ]]; then
  if [[ $PYTHONPATH = "" ]]; then
    echo "% export PYTHONPATH=$PY_SCRIPTING_DIR"
    export PYTHONPATH=$PY_SCRIPTING_DIR
  else
    echo "% export PYTHONPATH=$PYTHONPATH:$PY_SCRIPTING_DIR"
    export PYTHONPATH=$PYTHONPATH:$PY_SCRIPTING_DIR
  fi
fi
