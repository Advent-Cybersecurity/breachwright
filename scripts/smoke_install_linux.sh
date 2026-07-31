#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
    echo "Usage: smoke_install_linux.sh <bundle-directory>" >&2
    exit 2
fi

bundle_dir="$(cd "$1" && pwd)"
test_home="${RUNNER_TEMP:-/tmp}/breachwright-install-smoke-${GITHUB_RUN_ID:-local}-$$"
export HOME="$test_home"

cleanup() {
    case "$test_home" in
        "${RUNNER_TEMP:-/tmp}"/breachwright-install-smoke-*)
            rm -rf "$test_home"
            ;;
        *)
            echo "Refusing to clean an unexpected test path: $test_home" >&2
            ;;
    esac
}
trap cleanup EXIT

mkdir -p "$HOME"
bash "$bundle_dir/install.sh"

launcher="$HOME/.local/bin/breachwright"
install_dir="$HOME/.local/share/breachwright"
data_dir="$install_dir/data"

test -x "$launcher"
test -x "$install_dir/bin/Breachwright"
test -d "$data_dir/backups"
test "$("$launcher" --version)" = "Breachwright $(cat "$bundle_dir/VERSION")"

touch "$data_dir/preserved-marker"
printf 'y\n' | bash "$bundle_dir/uninstall.sh"

test ! -e "$launcher"
test ! -e "$install_dir/bin"
test -f "$data_dir/preserved-marker"

echo "Linux bundle install, version, uninstall, and data preservation passed"
