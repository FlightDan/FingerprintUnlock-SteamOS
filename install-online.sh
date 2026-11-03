#!/bin/sh
set -eu

COMMIT=fce3d1eef57154a005e9d2e8276d5c89426ca7f3
REPOSITORY=https://github.com/FlightDan/FingerprintUnlock-SteamOS.git

if [ "$(id -u)" -eq 0 ]; then
    echo 'Run this script as your normal user, without sudo.' >&2
    exit 1
fi
for dependency in git sudo; do
    if ! command -v "$dependency" >/dev/null 2>&1; then
        echo "Missing required command: $dependency" >&2
        exit 1
    fi
done

work=$(mktemp -d "${TMPDIR:-/tmp}/fingerprint-install.XXXXXXXX") || {
    echo 'Unable to create a temporary directory.' >&2
    exit 1
}
trap 'rm -rf -- "$work"' EXIT
trap 'exit 1' HUP INT TERM

git -C "$work" init -q
git -C "$work" fetch -q --depth 1 "$REPOSITORY" "$COMMIT"
actual=$(git -C "$work" rev-parse --verify 'FETCH_HEAD^{commit}')
if [ "$actual" != "$COMMIT" ]; then
    echo 'Downloaded commit does not match the reviewed commit.' >&2
    exit 1
fi
git -C "$work" checkout -q --detach "$COMMIT"
sudo sh "$work/install.sh" "$@"
