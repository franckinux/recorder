#!/usr/bin/env bash
set -e

if [[ -z $1 ]]; then
    RANGE="local"
elif [[ $# -eq 1 ]]; then
    if [[ $1 == "--local" || $1 == "-l" ]]; then
        RANGE="local"
    elif [[ $1 == "--user" || $1 == "-u" ]]; then
        RANGE="user"
    else
        echo "invalid option"
        exit 1
    fi
else
	 echo "invalid option number"
	 exit 1
fi

echo "pip list --$RANGE --outdated --format=freeze | grep -v '^\-e' | cut -d = -f 1 | xargs -n1 pip install -U"
