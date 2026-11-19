#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)
container_name=dictare-linux-ci

if docker container inspect "$container_name" >/dev/null 2>&1; then
    mounted_dir=$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/work"}}{{.Source}}{{end}}{{end}}' "$container_name")
    if [[ "$mounted_dir" != "$repo_dir" ]]; then
        printf 'Container %s belongs to a different checkout: %s\n' "$container_name" "$mounted_dir" >&2
        printf 'Remove or rename that container before using this checkout.\n' >&2
        exit 1
    fi
    init_enabled=$(docker inspect -f '{{.HostConfig.Init}}' "$container_name")
    if [[ "$init_enabled" != "true" ]]; then
        printf 'Container %s was created without Docker init; Xvfb can hang during startup.\n' "$container_name" >&2
        printf 'After any current test run finishes, remove it with: docker rm %s\n' "$container_name" >&2
        printf 'Then rerun this script to recreate it with the fix.\n' >&2
        exit 1
    fi
    container_command=$(docker inspect -f '{{json .Config.Cmd}}' "$container_name")
    if [[ "$container_command" != *'--cov-fail-under=90'* ]]; then
        printf 'Container %s has an outdated coverage gate.\n' "$container_name" >&2
        printf 'After any current test run finishes, remove it with: docker rm %s\n' "$container_name" >&2
        printf 'Then rerun this script to recreate it with the 90%% gate.\n' >&2
        exit 1
    fi
else
    docker build -t dictare-linux-ci - < "$repo_dir/scripts/linux/Dockerfile.ci"
    docker create --init --name "$container_name" --mount "type=bind,source=$repo_dir,target=/work" dictare-linux-ci >/dev/null
fi

docker start -a "$container_name"
