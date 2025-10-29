#!/bin/bash

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <config-file>"
    exit 1
fi

CONFIG_FILE=$1
export HAKO_DRONE_PROJECT_PATH=/Users/tmori/project/private/hakoniwa-drone-pro
export HAKO_ENVSIM_PATH=/Users/tmori/project/oss/hakoniwa-envsim
export HAKO_PANDA3D_DRONE_PATH=$(pwd)
python -m hakoniwa_pdu.apps.launcher.hako_launcher --mode immediate "$CONFIG_FILE"
