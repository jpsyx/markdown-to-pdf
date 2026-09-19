#!/usr/bin/env bash
# Install or update the command from this checkout.
set -euo pipefail

usage() {
  printf '%s\n' 'Install or update markdown-to-pdf as an executable command.

Usage: ./install.sh [--name <command>] [-h|--help]

Options:
  --name <command>  Command filename (default: markdown-to-pdf).
  -h, --help        Show this help without installing anything.

Environment:
  BIN_DIR          Installation directory (default: $HOME/.local/bin).

Examples:
  ./install.sh
  BIN_DIR="$HOME/bin" ./install.sh --name markdown-to-pdf-dev'
}

for arg in "$@"; do
  case "$arg" in -h|--help) usage; exit 0 ;; esac
done

command_name="markdown-to-pdf"
while (($#)); do
  case "$1" in
    --name)
      if (($# < 2)); then usage >&2; exit 2; fi
      command_name="$2"
      shift 2
      ;;
    *) usage >&2; exit 2 ;;
  esac
done
case "$command_name" in
  ''|[.-]*|*..*|*[!a-zA-Z0-9_.-]*) usage >&2; exit 2 ;;
esac
if ((${#command_name} > 100)); then usage >&2; exit 2; fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
bin_dir="${BIN_DIR:-$HOME/.local/bin}"
mkdir -p -- "$bin_dir"
bin_dir="$(cd -- "$bin_dir" && pwd)"
destination="$bin_dir/$command_name"
if [[ -d "$destination" ]]; then
  printf 'Cannot replace directory: %s\n' "$destination" >&2
  exit 1
fi
VENV="$script_dir/.venv"
PY="$VENV/bin/python"

# A virtualenv is bound to the interpreter it was built from, so an upgraded,
# switched, or removed Python leaves it dangling. Rebuild it whenever its
# interpreter no longer runs, which makes a broken install self-healing.
if [ ! -x "$PY" ] || ! "$PY" -c '' >/dev/null 2>&1; then
  command -v python3 >/dev/null 2>&1 || {
    echo "error: python3 not found; install Python 3 first" >&2
    exit 1
  }
  echo "Creating virtualenv at ${VENV}…" >&2
  rm -rf "$VENV"
  if ! python3 -m venv "$VENV" >&2; then
    echo "error: 'python3 -m venv' failed." >&2
    echo "       On Debian/Ubuntu the venv module ships separately:" >&2
    echo "         sudo apt install python3-venv" >&2
    exit 1
  fi
fi

# Needs network the first time (and whenever requirements.txt changes); pip
# resolves offline once everything is already satisfied.
echo "Installing dependencies…" >&2
"$PY" -m pip install --quiet --disable-pip-version-check -r "$script_dir/requirements.txt" >&2
"$PY" -c 'import reportlab' || {
  echo "error: dependencies did not install correctly into $VENV" >&2
  exit 1
}

# Mermaid diagrams need a headless browser, which is a Node toolchain rather
# than a Python one, so it is provisioned separately and never fatally: a
# document with no ```mermaid fence converts perfectly without it, and one with
# a fence degrades to printing the diagram source. Both installs are scoped to
# this clone plus puppeteer's shared cache; nothing is installed globally.
if command -v npm >/dev/null 2>&1; then
  echo "Installing the mermaid renderer…" >&2
  if npm install --prefix "$script_dir" >&2; then
    # puppeteer's own postinstall is commonly blocked by npm's allowScripts
    # policy, which leaves mermaid-cli with no browser to drive. Asking for the
    # browser explicitly works either way and overrides no security setting.
    if ! "$script_dir/node_modules/.bin/mmdc" --version >/dev/null 2>&1; then
      echo "note: mermaid-cli installed but not runnable yet" >&2
    fi
    npx --prefix "$script_dir" puppeteer browsers install chrome-headless-shell >&2 || {
      echo "note: could not fetch the headless browser mermaid needs." >&2
      echo "      Diagrams will print as source until this succeeds:" >&2
      echo "        cd $script_dir && npx puppeteer browsers install chrome-headless-shell" >&2
    }
  else
    echo "note: 'npm install' failed; mermaid diagrams will print as source." >&2
  fi
else
  echo >&2
  echo "note: npm not found, so mermaid diagrams will print as their source." >&2
  echo "      Install Node.js (https://nodejs.org), then re-run ./install.sh." >&2
fi

temporary="$(mktemp "$bin_dir/.install.XXXXXXXX")"
trap 'rm -f -- "$temporary"' EXIT
{
  printf '#!/usr/bin/env bash\n'
  printf 'run_sh=%q\n' "$script_dir/run.sh"
  printf '%s\n' \
    'if [[ ! -x "$run_sh" ]]; then' \
    '  printf "error: markdown-to-pdf is not where it was installed from (%s).\n" "$run_sh" >&2' \
    '  echo "       The clone was moved or deleted; re-run install.sh from it." >&2' \
    '  exit 1' \
    'fi' \
    'exec "$run_sh" "$@"'
} > "$temporary"
chmod 755 "$temporary"
mv -f -- "$temporary" "$destination"
[[ -f "$destination" && -x "$destination" ]]
printf 'Installed %s\n' "$destination"

# A launcher nobody can invoke is not an install. Say so, with the fix.
case ":${PATH}:" in
  *":$bin_dir:"*) ;;
  *)
    echo >&2
    echo "note: $bin_dir is not on your \$PATH, so \`$command_name\` won't be found yet." >&2
    echo "      Add it to your shell startup file, e.g.:" >&2
    echo "        echo 'export PATH=\"$bin_dir:\$PATH\"' >> ~/.zshrc   # or ~/.bashrc" >&2
    ;;
esac
