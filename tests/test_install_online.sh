#!/bin/sh
set -eu

SCRIPT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)/install-online.sh
ROOT=$(mktemp -d "${TMPDIR:-/tmp}/fingerprint-online-test.XXXXXXXX")
trap 'rm -rf -- "$ROOT"' EXIT
mkdir "$ROOT/bin" "$ROOT/tmp"
export ROOT
export TMPDIR="$ROOT/tmp"
export PATH="$ROOT/bin:$PATH"

cat > "$ROOT/bin/id" <<'EOF'
#!/bin/sh
echo "${MOCK_UID:-1000}"
EOF
cat > "$ROOT/bin/git" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >> "$ROOT/git.log"
case " $* " in
  *' fetch '*) [ "${MOCK_FETCH_FAIL:-0}" = 0 ] || exit 1 ;;
  *' rev-parse '*) printf '%s\n' "${MOCK_COMMIT:-fce3d1eef57154a005e9d2e8276d5c89426ca7f3}" ;;
esac
EOF
cat > "$ROOT/bin/sudo" <<'EOF'
#!/bin/sh
printf '%s\n' "$@" > "$ROOT/sudo.log"
exit "${MOCK_SUDO_EXIT:-0}"
EOF
if command -v chmod >/dev/null 2>&1; then
    chmod +x "$ROOT/bin/id" "$ROOT/bin/git" "$ROOT/bin/sudo"
fi

sh "$SCRIPT" --fprintd-bin '/path with spaces' 'literal $value'
test "$(sed -n '1p' "$ROOT/sudo.log")" = sh
case "$(sed -n '2p' "$ROOT/sudo.log")" in "$ROOT/tmp"/fingerprint-install.*/install.sh) ;; *) exit 1 ;; esac
test "$(sed -n '3p' "$ROOT/sudo.log")" = --fprintd-bin
test "$(sed -n '4p' "$ROOT/sudo.log")" = '/path with spaces'
test "$(sed -n '5p' "$ROOT/sudo.log")" = 'literal $value'
test -z "$(ls -A "$ROOT/tmp")"
grep -q 'fetch -q --depth 1 https://github.com/FlightDan/FingerprintUnlock-SteamOS.git fce3d1eef57154a005e9d2e8276d5c89426ca7f3' "$ROOT/git.log"

rm "$ROOT/sudo.log"
if MOCK_COMMIT=0000000000000000000000000000000000000000 sh "$SCRIPT" 2>"$ROOT/error.log"; then
    echo 'A mismatched commit was accepted.' >&2
    exit 1
fi
test ! -e "$ROOT/sudo.log"
test -z "$(ls -A "$ROOT/tmp")"
grep -q 'does not match' "$ROOT/error.log"
if MOCK_FETCH_FAIL=1 sh "$SCRIPT"; then
    echo 'A failed fetch was accepted.' >&2
    exit 1
fi
test ! -e "$ROOT/sudo.log"
test -z "$(ls -A "$ROOT/tmp")"
if MOCK_UID=0 sh "$SCRIPT" 2>"$ROOT/error.log"; then
    echo 'Root execution was accepted.' >&2
    exit 1
fi
grep -q 'without sudo' "$ROOT/error.log"
if MOCK_SUDO_EXIT=7 sh "$SCRIPT"; then
    echo 'A failed installer was accepted.' >&2
    exit 1
fi
test -z "$(ls -A "$ROOT/tmp")"
echo 'Online installer simulation passed.'
