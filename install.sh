#!/usr/bin/env bash
set -euo pipefail

# --- Defaults ---
PREFIX="${HOME}/.local"
SOURCE=""

# --- Help ---
usage() {
    cat <<EOF
Usage: $0 --prefix <path> <REPO-URL|local-path>

Install kubux-mail-client from a git repository or local directory.

Examples:
  $0 --prefix ~/.local https://gitlab.kubux.net/kubux/programming/programs/kubux-mail-client.git
  $0 --prefix ~/.local .   # install from current directory

Options:
  --prefix <path>   Installation prefix (default: \$HOME/.local)
  -h, --help        Show this help
EOF
    exit 0
}

# --- Parse args ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        --prefix)
            if [[ -z "${2:-}" ]]; then
                echo "ERROR: --prefix requires a path argument" >&2
                exit 1
            fi
            PREFIX="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            if [[ -n "$SOURCE" ]]; then
                echo "ERROR: Unexpected argument: $1" >&2
                exit 1
            fi
            SOURCE="$1"
            shift
            ;;
    esac
done

if [[ -z "$SOURCE" ]]; then
    echo "ERROR: No source specified. Provide a git URL or local path." >&2
    usage
fi

# --- Resolve source ---
TMPDIR=""
INSTALL_SRC=""

if [[ -d "$SOURCE" ]]; then
    INSTALL_SRC="$(cd "$SOURCE" && pwd)"
    echo "Installing from local directory: $INSTALL_SRC"
elif [[ "$SOURCE" =~ ^https?:// || "$SOURCE" =~ ^git@ ]]; then
    TMPDIR="$(mktemp -d)"
    echo "Cloning $SOURCE ..."
    git clone --depth=1 "$SOURCE" "$TMPDIR"
    INSTALL_SRC="$TMPDIR"
else
    echo "ERROR: '$SOURCE' is neither a directory nor a git URL." >&2
    exit 1
fi

# --- Check system dependencies (warn only) ---
echo ""
echo "--- Checking system dependencies ---"

MISSING=""
check_dep() {
    if ! command -v "$1" &>/dev/null; then
        echo "  WARNING: '$1' not found. Install it for full functionality."
        MISSING="$MISSING $1"
    else
        echo "  OK: $1 found"
    fi
}

check_dep python3
check_dep notmuch
check_dep mbsync
check_dep msmtp
check_dep gpg
check_dep jq
check_dep convert
check_dep notify-send
check_dep git
check_dep gcc
check_dep make
check_dep pkg-config

echo ""

# --- Create directories ---
BINDIR="${PREFIX}/bin"
SHAREDIR="${PREFIX}/share"
VENVDIR="${PREFIX}/lib/kubux-mail-client/venv"
APPDIR="${SHAREDIR}/applications"
ICONDIR="${SHAREDIR}/icons/hicolor"

mkdir -p "$BINDIR" "$APPDIR" "$ICONDIR"

# --- Create Python virtualenv and install dependencies ---
echo "--- Setting up Python virtualenv ---"
python3 -m venv --clear "$VENVDIR"
source "${VENVDIR}/bin/activate"

echo "Installing Python dependencies via pip ..."
python3 -m pip install --quiet --upgrade pip

# Install packages that don't need special build deps first
python3 -m pip install --quiet \
    PySide6 \
    scikit-learn \
    toml \
    imapclient \
    watchdog \
    mail-parser \
    html2text \
    beautifulsoup4

# --- notmuch2: build from source if not already available ---
if python3 -c "import notmuch2" 2>/dev/null; then
    echo "  notmuch2 already available, skipping."
else
    echo "  notmuch2 not found. Building notmuch from source ..."

    NOTMUCH_SRC="$VENVDIR/build/notmuch"
    mkdir -p "$VENVDIR/build"

    # Use GitHub mirror of notmuch (official git.notmuchmail.org may be slow)
    if [[ -d "$INSTALL_SRC/.git" ]] && [[ -f "$INSTALL_SRC/version.txt" ]]; then
        # The repo itself is the notmuch source (unlikely but check)
        ln -sf "$INSTALL_SRC" "$NOTMUCH_SRC"
    else
        echo "  Cloning notmuch source ..."
        git clone --depth=1 https://github.com/notmuch/notmuch.git "$NOTMUCH_SRC" 2>/dev/null || \
        git clone --depth=1 git://notmuchmail.org/git/notmuch "$NOTMUCH_SRC" 2>/dev/null || {
            echo "  WARNING: Failed to clone notmuch source. notmuch2 will be missing."
            echo "  You can install it later manually."
            NOTMUCH_SRC=""
        }
    fi

    if [[ -n "$NOTMUCH_SRC" ]] && [[ -f "$NOTMUCH_SRC/version.txt" ]]; then
        pushd "$NOTMUCH_SRC" >/dev/null

        # Try to configure and build notmuch C library
        if ./configure --prefix="$VENVDIR" 2>&1 | tail -5; then
            echo "  Building notmuch library ..."
            make -j"$(nproc)" 2>&1 | tail -5
            make install 2>&1 | tail -5
            echo "  notmuch C library installed to $VENVDIR"
        else
            echo "  WARNING: notmuch configure failed. Will try pip with source tree."
        fi
        popd >/dev/null

        # Install notmuch2 Python bindings from the bundled source
        if [[ -d "$NOTMUCH_SRC/bindings/python-cffi" ]]; then
            echo "  Building notmuch2 Python bindings ..."
            pushd "$NOTMUCH_SRC/bindings/python-cffi" >/dev/null
            PKG_CONFIG_PATH="$VENVDIR/lib/pkgconfig:${PKG_CONFIG_PATH:-}" \
            LD_LIBRARY_PATH="$VENVDIR/lib:${LD_LIBRARY_PATH:-}" \
            CFLAGS="-I$VENVDIR/include" \
            LDFLAGS="-L$VENVDIR/lib" \
            python3 -m pip install --quiet . 2>&1 | tail -5 || \
            echo "  WARNING: notmuch2 build failed. Install it manually."
            popd >/dev/null
        fi
    fi
fi

deactivate
echo "Python virtualenv ready at $VENVDIR"
echo ""

# --- Copy scripts ---
echo "--- Installing scripts ---"
cp -P "$INSTALL_SRC"/scripts/*.py "$BINDIR/"
cp -P "$INSTALL_SRC"/scripts/*.jq "$BINDIR/" 2>/dev/null || true
cp -P "$INSTALL_SRC"/scripts/predict-tags "$BINDIR/" 2>/dev/null || true
cp -P "$INSTALL_SRC"/scripts/decrypt-on-the-fly "$BINDIR/" 2>/dev/null || true
cp -P "$INSTALL_SRC"/scripts/mbsync-and-decrypt "$BINDIR/" 2>/dev/null || true
chmod +x "$BINDIR"/*.py 2>/dev/null || true
chmod +x "$BINDIR"/predict-tags 2>/dev/null || true
chmod +x "$BINDIR"/decrypt-on-the-fly 2>/dev/null || true
chmod +x "$BINDIR"/mbsync-and-decrypt 2>/dev/null || true

# Fix shebang in predict-tags to use venv python
if [[ -f "$BINDIR/predict-tags" ]]; then
    sed -i "s|^python |${VENVDIR}/bin/python |" "$BINDIR/predict-tags"
fi

# --- Create wrapper scripts ---
echo "Creating wrapper scripts ..."
WRAP_SCRIPTS=(
    ai-classify ai-train edit-mail wait-for-change
    view-mail view-thread open-drafts manage-mail
    show-query-results send-mail get-message-id
    pause-imap-sync config-helper-get-pixel-ratio
    config-helper-get-dpi
)

for name in "${WRAP_SCRIPTS[@]}"; do
    wrapper="${BINDIR}/${name}"
    cat > "$wrapper" <<WRAPEOF
#!/usr/bin/env bash
export TMPDIR="\${TMPDIR:-/tmp}"
export LD_LIBRARY_PATH="${VENVDIR}/lib:\${LD_LIBRARY_PATH:-}"
exec "${VENVDIR}/bin/python" "${BINDIR}/${name}.py" "\$@"
WRAPEOF
    chmod +x "$wrapper"
done

echo "Scripts installed to $BINDIR"
echo ""

# --- Install .desktop file ---
echo "--- Installing desktop file ---"
DESKTOP_SRC="${INSTALL_SRC}/kubux-mail-client.desktop"
if [[ -f "$DESKTOP_SRC" ]]; then
    sed \
        -e "s|^Exec=show-query-results|Exec=${BINDIR}/show-query-results|" \
        -e "s|^Exec=manage-mail|Exec=${BINDIR}/manage-mail|" \
        "$DESKTOP_SRC" > "${APPDIR}/kubux-mail-client.desktop"
    echo "Desktop file installed to ${APPDIR}/kubux-mail-client.desktop"
else
    echo "WARNING: kubux-mail-client.desktop not found, skipping."
fi
echo ""

# --- Install icons ---
echo "--- Installing icons ---"
ICON_SRC="${INSTALL_SRC}/app-icon.png"
if [[ -f "$ICON_SRC" ]] && command -v convert &>/dev/null; then
    for size in 16x16 22x22 24x24 32x32 48x48 64x64 96x96 128x128 192x192 256x256; do
        sizedir="${ICONDIR}/${size}/apps"
        mkdir -p "$sizedir"
        convert "$ICON_SRC" -resize "$size" "${sizedir}/kubux-mail-client.png"
    done
    echo "Icons installed to $ICONDIR"
elif [[ -f "$ICON_SRC" ]]; then
    echo "WARNING: ImageMagick (convert) not found. Copying icon as-is."
    mkdir -p "${ICONDIR}/256x256/apps"
    cp "$ICON_SRC" "${ICONDIR}/256x256/apps/kubux-mail-client.png"
else
    echo "WARNING: app-icon.png not found, skipping icons."
fi
echo ""

# --- Cleanup ---
if [[ -n "$TMPDIR" ]]; then
    rm -rf "$TMPDIR"
fi

# --- Done ---
echo "============================================"
echo "Installation complete!"
echo ""
echo "  Prefix: $PREFIX"
echo "  Binaries: $BINDIR"
echo ""
echo "Make sure $BINDIR is in your PATH."
echo "You can add this to your ~/.bashrc or ~/.profile:"
echo ""
echo "  export PATH=\"\$PATH:${BINDIR}\""
echo ""
echo "Then run: show-query-results"
echo "============================================"