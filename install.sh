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

# --- Create directories ---
BINDIR="${PREFIX}/bin"
SHAREDIR="${PREFIX}/share"
VENVDIR="${PREFIX}/lib/kubux-mail-client/venv"
APPDIR="${SHAREDIR}/applications"
ICONDIR="${SHAREDIR}/icons/hicolor"
BUILDDIR="${VENVDIR}/build"

mkdir -p "$BINDIR" "$APPDIR" "$ICONDIR" "$BUILDDIR"

export PKG_CONFIG_PATH="$VENVDIR/lib/pkgconfig:${PKG_CONFIG_PATH:-}"
export LD_LIBRARY_PATH="$VENVDIR/lib:${LD_LIBRARY_PATH:-}"
export CFLAGS="-I$VENVDIR/include"
export LDFLAGS="-L$VENVDIR/lib"
export PATH="$VENVDIR/bin:$PATH"

# --- Build helpers ---
build_autoconf() {
    local name="$1"
    local url="$2"
    local dirname="$3"
    local src_dir="$BUILDDIR/$dirname"
    shift 3

    if [[ -f "$VENVDIR/lib/pkgconfig/${1:-}" ]]; then
        return 0
    fi
    echo "  Building $name ..."
    mkdir -p "$src_dir"
    pushd "$src_dir" >/dev/null
    curl -sL "$url" | tar xz --strip-components=1 -C "$src_dir" 2>/dev/null || {
        echo "  WARNING: Failed to download $name"
        popd >/dev/null
        return 1
    }
    ./configure --prefix="$VENVDIR" "$@" 2>&1 || {
        echo "  WARNING: configure failed for $name"
        popd >/dev/null
        return 1
    }
    make -j"$(nproc)" 2>&1
    make install 2>&1
    popd >/dev/null
    echo "  $name built."
}

# --- Build notmuch dependencies ---

# talloc
if ! pkg-config --exists talloc 2>/dev/null; then
    echo "  Building talloc ..."
    TALLOC_SRC="$BUILDDIR/talloc"
    mkdir -p "$TALLOC_SRC"
    pushd "$TALLOC_SRC" >/dev/null
    curl -sL https://download.samba.org/pub/talloc/talloc-2.4.2.tar.gz | tar xz --strip-components=1 -C "$TALLOC_SRC" 2>/dev/null || true
    if [[ -f configure ]]; then
        ./configure --prefix="$VENVDIR"
        make -j"$(nproc)"
        make install
    fi
    popd >/dev/null
    echo "  talloc built."
fi

# Xapian
if ! pkg-config --exists xapian-core 2>/dev/null; then
    echo "  Building Xapian ..."
    XAPIAN_SRC="$BUILDDIR/xapian"
    mkdir -p "$XAPIAN_SRC"
    pushd "$XAPIAN_SRC" >/dev/null
    curl -sL https://oligarchy.co.uk/xapian/1.4.27/xapian-core-1.4.27.tar.xz | tar xJ --strip-components=1 -C "$XAPIAN_SRC" 2>/dev/null || true
    if [[ -f configure ]]; then
        ./configure --prefix="$VENVDIR"
        make -j"$(nproc)"
        make install
    fi
    popd >/dev/null
    echo "  Xapian built."
fi

# libgpg-error (needed by GPGME)
if ! pkg-config --exists gpg-error 2>/dev/null; then
    echo "  Building libgpg-error ..."
    GPGERR_SRC="$BUILDDIR/libgpg-error"
    mkdir -p "$GPGERR_SRC"
    pushd "$GPGERR_SRC" >/dev/null
    curl -sL https://www.gnupg.org/ftp/gcrypt/libgpg-error/libgpg-error-1.51.tar.bz2 | tar xj --strip-components=1 -C "$GPGERR_SRC" 2>/dev/null || true
    if [[ -f configure ]]; then
        ./configure --prefix="$VENVDIR"
        make -j"$(nproc)"
        make install
    fi
    popd >/dev/null
    echo "  libgpg-error built."
fi

# libassuan (needed by GPGME)
if ! pkg-config --exists libassuan 2>/dev/null; then
    echo "  Building libassuan ..."
    ASSUAN_SRC="$BUILDDIR/libassuan"
    mkdir -p "$ASSUAN_SRC"
    pushd "$ASSUAN_SRC" >/dev/null
    curl -sL https://www.gnupg.org/ftp/gcrypt/libassuan/libassuan-3.0.2.tar.bz2 | tar xj --strip-components=1 -C "$ASSUAN_SRC" 2>/dev/null || true
    if [[ -f configure ]]; then
        ./configure --prefix="$VENVDIR"
        make -j"$(nproc)"
        make install
    fi
    popd >/dev/null
    echo "  libassuan built."
fi

# GPGME
if ! pkg-config --exists gpgme 2>/dev/null; then
    echo "  Building GPGME ..."
    GPGME_SRC="$BUILDDIR/gpgme"
    mkdir -p "$GPGME_SRC"
    pushd "$GPGME_SRC" >/dev/null
    curl -sL https://www.gnupg.org/ftp/gcrypt/gpgme/gpgme-1.24.2.tar.bz2 | tar xj --strip-components=1 -C "$GPGME_SRC" 2>/dev/null || true
    if [[ -f configure ]]; then
        ./configure --prefix="$VENVDIR" --disable-gpg-test --disable-g13-test --disable-gpgsm-test
        make -j"$(nproc)"
        make install
    fi
    popd >/dev/null
    echo "  GPGME built."
fi

# GMime
if ! pkg-config --exists gmime-3.0 2>/dev/null; then
    echo "  Building GMime ..."
    GMIME_SRC="$BUILDDIR/gmime"
    mkdir -p "$GMIME_SRC"
    pushd "$GMIME_SRC" >/dev/null
    curl -sL https://download.gnome.org/sources/gmime/3.2/gmime-3.2.15.tar.xz | tar xJ --strip-components=1 -C "$GMIME_SRC" 2>/dev/null || true
    if [[ -f configure ]]; then
        ./configure --prefix="$VENVDIR" --disable-gtk-doc ac_cv_path_GTKDOC=no
        make -j"$(nproc)"
        make install
    fi
    popd >/dev/null
    echo "  GMime built."
fi

# notmuch
if ! command -v notmuch &>/dev/null; then
    echo "  Building notmuch from source ..."
    NOTMUCH_SRC="$BUILDDIR/notmuch"
    git clone --depth=1 https://github.com/notmuch/notmuch.git "$NOTMUCH_SRC" 2>/dev/null || \
    git clone --depth=1 git://notmuchmail.org/git/notmuch "$NOTMUCH_SRC" 2>/dev/null || true
    if [[ -f "$NOTMUCH_SRC/version.txt" ]]; then
        pushd "$NOTMUCH_SRC" >/dev/null
        # Set cross_compiling=yes to skip runtime crypto checks on GMime
        # (the locally-built GMime/GPGME lacks gpg-agent etc. for runtime tests)
        cross_compiling=yes ./configure --prefix="$VENVDIR"
        make -j"$(nproc)"
        make install
        popd >/dev/null
        echo "  notmuch built."
    fi
fi

# mbsync (isync)
if ! command -v mbsync &>/dev/null; then
    echo "  Building mbsync from source ..."
    MBSYNC_SRC="$BUILDDIR/isync"
    git clone --depth=1 https://github.com/yaoweibin/isync.git "$MBSYNC_SRC" 2>/dev/null || true
    if [[ -f "$MBSYNC_SRC/configure.ac" ]] || [[ -f "$MBSYNC_SRC/configure" ]]; then
        pushd "$MBSYNC_SRC" >/dev/null
        if [[ ! -f configure ]]; then
            autoreconf -fi
        fi
        ./configure --prefix="$VENVDIR"
        make -j"$(nproc)"
        make install
        popd >/dev/null
        echo "  mbsync built."
    fi
fi

# msmtp
if ! command -v msmtp &>/dev/null; then
    echo "  Building msmtp from source ..."
    MSMTP_SRC="$BUILDDIR/msmtp"
    curl -sL https://marlam.de/msmtp/releases/msmtp-1.8.25.tar.xz | tar xJ -C "$BUILDDIR" 2>/dev/null || true
    if [[ -d "$BUILDDIR/msmtp-1.8.25" ]]; then
        mv "$BUILDDIR/msmtp-1.8.25" "$MSMTP_SRC" 2>/dev/null || true
    fi
    if [[ -f "$MSMTP_SRC/configure" ]]; then
        pushd "$MSMTP_SRC" >/dev/null
        ./configure --prefix="$VENVDIR" --without-libgnutls --with-ssl=openssl || \
        ./configure --prefix="$VENVDIR"
        make -j"$(nproc)"
        make install
        popd >/dev/null
        echo "  msmtp built."
    fi
fi

# --- Create Python virtualenv ---
echo "--- Setting up Python virtualenv ---"
if python3 -m venv --help 2>/dev/null | grep -q -- --without-pip; then
    python3 -m venv --without-pip "$VENVDIR"
else
    python3 -m venv "$VENVDIR" 2>/dev/null || {
        python3 -m virtualenv "$VENVDIR" 2>/dev/null || {
            pip3 install --user virtualenv 2>/dev/null || true
            python3 -m virtualenv "$VENVDIR" 2>/dev/null || true
        }
    }
fi
source "${VENVDIR}/bin/activate"

# Install pip if not present
if ! python3 -m pip --version &>/dev/null; then
    echo "  Installing pip ..."
    curl -sL https://bootstrap.pypa.io/get-pip.py -o "$BUILDDIR/get-pip.py"
    python3 "$BUILDDIR/get-pip.py"
fi

echo "  Installing Python dependencies ..."
python3 -m pip install --quiet --upgrade pip

python3 -m pip install --quiet \
    PySide6 \
    scikit-learn \
    toml \
    imapclient \
    watchdog \
    mail-parser \
    html2text \
    beautifulsoup4

# --- notmuch2 ---
if ! python3 -c "import notmuch2" 2>/dev/null; then
    NOTMUCH_SRC="$BUILDDIR/notmuch"
    if [[ -d "$NOTMUCH_SRC/bindings/python-cffi" ]]; then
        echo "  Building notmuch2 Python bindings ..."
        pushd "$NOTMUCH_SRC/bindings/python-cffi" >/dev/null
        python3 -m pip install --quiet . || true
        popd >/dev/null
    fi
fi

deactivate
echo "  Python virtualenv ready."
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
export PKG_CONFIG_PATH="${VENVDIR}/lib/pkgconfig:\${PKG_CONFIG_PATH:-}"
exec "${VENVDIR}/bin/python" "${BINDIR}/${name}.py" "\$@"
WRAPEOF
    chmod +x "$wrapper"
done

echo "  Scripts installed to $BINDIR"
echo ""

# --- Install .desktop file ---
echo "--- Installing desktop file ---"
DESKTOP_SRC="${INSTALL_SRC}/kubux-mail-client.desktop"
if [[ -f "$DESKTOP_SRC" ]]; then
    sed \
        -e "s|^Exec=show-query-results|Exec=${BINDIR}/show-query-results|" \
        -e "s|^Exec=manage-mail|Exec=${BINDIR}/manage-mail|" \
        "$DESKTOP_SRC" > "${APPDIR}/kubux-mail-client.desktop"
    echo "  Desktop file installed."
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
    echo "  Icons installed."
elif [[ -f "$ICON_SRC" ]]; then
    mkdir -p "${ICONDIR}/256x256/apps"
    cp "$ICON_SRC" "${ICONDIR}/256x256/apps/kubux-mail-client.png"
    echo "  Icon copied."
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