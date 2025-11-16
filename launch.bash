#!/bin/bash

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <config-file>"
    exit 1
fi

CONFIG_FILE=$1
OS=$(uname)

if [ "$OS" == "Darwin" ]; then
    export HAKO_DRONE_PROJECT_PATH=/Users/tmori/project/private/hakoniwa-drone-pro
    export HAKO_ENVSIM_PATH=/Users/tmori/project/oss/hakoniwa-envsim
    export PYTHON_PATH=/Users/tmori/.pyenv/versions/3.12.3/bin/python
    export HAKO_PANDA3D_DRONE_PATH=$(pwd)
    python -m hakoniwa_pdu.apps.launcher.hako_launcher --mode immediate "$CONFIG_FILE"

else
    export HAKO_DRONE_PROJECT_PATH=${HOME}/workspace/hakoniwa-drone-pro
    export HAKO_ENVSIM_PATH=${HOME}/workspace/hakoniwa-envsim
    export PYTHON_PATH=python3
    export HAKO_PANDA3D_DRONE_PATH=$(pwd)
    python3 -m hakoniwa_pdu.apps.launcher.hako_launcher --mode immediate "$CONFIG_FILE"
fi
