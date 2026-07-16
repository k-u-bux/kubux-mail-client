#!/usr/bin/env bash
set -euo pipefail

PREFIX="${HOME}/.local"
SOURCE=""

usage() {
    cat <<EOF
Usage: $0 --prefix <path> <REPO-URL|local-path>

Install kubux-mail-client from git or local directory.

Examples:
  $0 --prefix ~/.local https://gitlab.kubux.net/kubux/programming/programs/kubux-mail-client.git
  $0 --prefix ~/.local .

Options:
  --prefix <path>   Installation prefix (default: \$HOME/.local)
  -h, --help        Show this help
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --prefix) PREFIX="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) SOURCE="$1"; shift ;;
    esac
done

[[ -n "$SOURCE" ]] || { echo "ERROR: No source specified." >&2; usage; }

if [[ -d "$SOURCE" ]]; then
    INSTALL_SRC="$(cd "$SOURCE" && pwd)"
elif [[ "$SOURCE" =~ ^https?:// || "$SOURCE" =~ ^git@ ]]; then
    TMPDIR="$(mktemp -d)"
    git clone --depth=1 "$SOURCE" "$TMPDIR"
    INSTALL_SRC="$TMPDIR"
else
    echo "ERROR: '$SOURCE' is neither a directory nor a git URL." >&2; exit 1
fi

BINDIR="${PREFIX}/bin"
VENVDIR="${PREFIX}/lib/kubux-mail-client/venv"
BUILDDIR="${VENVDIR}/build"
APPDIR="${PREFIX}/share/applications"
ICONDIR="${PREFIX}/share/icons/hicolor"

mkdir -p "$BINDIR" "$APPDIR" "$ICONDIR" "$BUILDDIR"

export PKG_CONFIG_PATH="$VENVDIR/lib/pkgconfig:$VENVDIR/lib64/pkgconfig:${PKG_CONFIG_PATH:-}"
export LD_LIBRARY_PATH="$VENVDIR/lib:$VENVDIR/lib64:${LD_LIBRARY_PATH:-}"
export CFLAGS="-I$VENVDIR/include"
export LDFLAGS="-L$VENVDIR/lib -L$VENVDIR/lib64"
export PATH="$VENVDIR/bin:$PATH"

# --- Build dependencies ---

build_src() {
    local name="$1" url="$2" dir="$3"
    shift 3
    local src="$BUILDDIR/$dir"
    echo "  Building $name ..."
    rm -rf "$src"; mkdir -p "$src"; pushd "$src" >/dev/null
    curl -sL "$url" | tar xz --strip-components=1 -C "$src" 2>/dev/null || { popd >/dev/null; echo "  WARNING: $name download failed"; return 1; }
    ./configure --prefix="$VENVDIR" "$@" 2>&1 || { popd >/dev/null; echo "  WARNING: $name configure failed"; return 1; }
    make -j"$(nproc)" 2>&1; make install 2>&1; popd >/dev/null
    echo "  $name built."
}

pkg-config --exists talloc 2>/dev/null || build_src talloc \
  https://download.samba.org/pub/talloc/talloc-2.4.2.tar.gz talloc

# Xapian - try primary mirror, fallback to oligarchy.co.uk
if ! pkg-config --exists xapian-core 2>/dev/null; then
    echo "  Building xapian ..."
    src="$BUILDDIR/xapian"
    rm -rf "$src"; mkdir -p "$src"; pushd "$src" >/dev/null
    if ! curl -sL https://downloads.xapian.org/releases/xapian-core-1.4.27.tar.xz | tar xJ --strip-components=1 -C "$src" 2>/dev/null; then
        curl -sL https://oligarchy.co.uk/xapian/1.4.27/xapian-core-1.4.27.tar.xz | tar xJ --strip-components=1 -C "$src" 2>/dev/null || true
    fi
    if [[ -f configure ]]; then
        ./configure --prefix="$VENVDIR" 2>&1
        make -j"$(nproc)" 2>&1; make install 2>&1
        popd >/dev/null; echo "  xapian built."
    else
        popd >/dev/null; echo "  WARNING: xapian download failed"; echo "  xapian skipped."
    fi
fi

pkg-config --exists gpg-error 2>/dev/null || {
    echo "  Building libgpg-error ..."
    src="$BUILDDIR/libgpg-error"
    rm -rf "$src"; mkdir -p "$src"; pushd "$src" >/dev/null
    curl -sL https://www.gnupg.org/ftp/gcrypt/libgpg-error/libgpg-error-1.51.tar.bz2 | tar xj --strip-components=1 -C "$src" 2>/dev/null || true
    [[ -f configure ]] && { ./configure --prefix="$VENVDIR"; make -j"$(nproc)"; make install; }
    popd >/dev/null; echo "  libgpg-error built."
}

pkg-config --exists libassuan 2>/dev/null || {
    echo "  Building libassuan ..."
    src="$BUILDDIR/libassuan"
    rm -rf "$src"; mkdir -p "$src"; pushd "$src" >/dev/null
    curl -sL https://www.gnupg.org/ftp/gcrypt/libassuan/libassuan-3.0.2.tar.bz2 | tar xj --strip-components=1 -C "$src" 2>/dev/null || true
    [[ -f configure ]] && { ./configure --prefix="$VENVDIR"; make -j"$(nproc)"; make install; }
    popd >/dev/null; echo "  libassuan built."
}

pkg-config --exists gpgme 2>/dev/null || {
    echo "  Building GPGME ..."
    src="$BUILDDIR/gpgme"
    rm -rf "$src"; mkdir -p "$src"; pushd "$src" >/dev/null
    curl -sL https://www.gnupg.org/ftp/gcrypt/gpgme/gpgme-1.24.2.tar.bz2 | tar xj --strip-components=1 -C "$src" 2>/dev/null || true
    [[ -f configure ]] && { ./configure --prefix="$VENVDIR" --disable-gpg-test --disable-g13-test --disable-gpgsm-test; make -j"$(nproc)"; make install; }
    popd >/dev/null; echo "  GPGME built."
}

pkg-config --exists gmime-3.0 2>/dev/null || {
    echo "  Building GMime ..."
    src="$BUILDDIR/gmime"
    rm -rf "$src"; mkdir -p "$src"; pushd "$src" >/dev/null
    if ! curl -sL https://download.gnome.org/sources/gmime/3.2/gmime-3.2.7.tar.xz | tar xJ --strip-components=1 -C "$src" 2>/dev/null; then
        echo "  WARNING: GMime download failed"
        popd >/dev/null; echo "  GMime skipped."
    else
        # Create fake gtk-doc in PATH so configure doesn't error out
        mkdir -p "$BUILDDIR/bin"
        cat > "$BUILDDIR/bin/gtk-doc" << 'EOF'
#!/bin/sh
echo "gtk-doc (fake) 1.33"
exit 0
EOF
        chmod +x "$BUILDDIR/bin/gtk-doc"
        PATH="$BUILDDIR/bin:$PATH" ./configure --prefix="$VENVDIR" --disable-gtk-doc 2>&1 || true
        if [[ -f Makefile ]]; then
            make -j"$(nproc)" 2>&1; make install 2>&1
            popd >/dev/null; echo "  GMime built."
        else
            popd >/dev/null; echo "  WARNING: GMime configure failed"; echo "  GMime skipped."
        fi
    fi
}

if ! command -v notmuch &>/dev/null; then
    echo "  Building notmuch from source ..."
    src="$BUILDDIR/notmuch"
    git clone --depth=1 https://github.com/notmuch/notmuch.git "$src" 2>/dev/null || \
    git clone --depth=1 git://notmuchmail.org/git/notmuch "$src" 2>/dev/null || true
    if [[ -f "$src/version.txt" ]]; then
        pushd "$src" >/dev/null
        # Patch configure: reset errors so Makefile.config is generated
        # even if GMime runtime crypto tests fail (no gpg-agent in sandbox).
        sed -i 's/^if \[ \$errors -gt 0 \]; then$/errors=0; if [ \$errors -gt 0 ]; then/' configure || true
        # Ensure gmime_cflags is set even if GMime not found (avoids unset var error)
        gmime_cflags="" gmime_ldflags="" ./configure --prefix="$VENVDIR"
        # Fix GMime crypto config vars that configure may have set to 0
        sed -i -e 's/^NOTMUCH_GMIME_X509_CERT_VALIDITY=.*/NOTMUCH_GMIME_X509_CERT_VALIDITY=1/' \
               -e 's/^NOTMUCH_GMIME_VERIFY_WITH_SESSION_KEY=.*/NOTMUCH_GMIME_VERIFY_WITH_SESSION_KEY=1/' \
               Makefile.config 2>/dev/null || true
        make -j"$(nproc)"
        make install
        popd >/dev/null
        echo "  notmuch built."
    fi
fi

if ! command -v mbsync &>/dev/null; then
    echo "  Building mbsync from source ..."
    src="$BUILDDIR/isync"
    rm -rf "$src"; mkdir -p "$src"; pushd "$src" >/dev/null
    curl -sL https://downloads.sourceforge.net/project/isync/isync/1.5.0/isync-1.5.0.tar.gz | tar xz --strip-components=1 -C "$src" 2>/dev/null || true
    [[ -f configure ]] && { ./configure --prefix="$VENVDIR"; make -j"$(nproc)"; make install; }
    popd >/dev/null; echo "  mbsync built."
fi

if ! command -v msmtp &>/dev/null; then
    echo "  Building msmtp from source ..."
    src="$BUILDDIR/msmtp"
    rm -rf "$src"; mkdir -p "$src"; pushd "$src" >/dev/null
    curl -sL https://marlam.de/msmtp/releases/msmtp-1.8.25.tar.xz | tar xJ --strip-components=1 -C "$src" 2>/dev/null || true
    [[ -f configure ]] && { ./configure --prefix="$VENVDIR" --without-libgnutls --with-ssl=openssl || ./configure --prefix="$VENVDIR"; make -j"$(nproc)"; make install; }
    popd >/dev/null; echo "  msmtp built."
fi

# muchsync needs sqlite3 and openssl
if ! pkg-config --exists sqlite3 2>/dev/null; then
    echo "  Building sqlite3 from source ..."
    src="$BUILDDIR/sqlite3"
    rm -rf "$src"; mkdir -p "$src"; pushd "$src" >/dev/null
    curl -sL https://sqlite.org/2025/sqlite-autoconf-3490100.tar.gz | tar xz --strip-components=1 -C "$src" 2>/dev/null || true
    if [[ -f "$src/configure" ]]; then
        ./configure --prefix="$VENVDIR" 2>&1
        make -j"$(nproc)" 2>&1
        make install 2>&1
    else
        echo "  WARNING: sqlite3 download failed"
    fi
    popd >/dev/null; echo "  sqlite3 built."
fi

if ! pkg-config --exists libcrypto 2>/dev/null; then
    echo "  Building openssl from source ..."
    src="$BUILDDIR/openssl"
    rm -rf "$src"; mkdir -p "$src"; pushd "$src" >/dev/null
    curl -sL https://github.com/openssl/openssl/releases/download/openssl-3.5.0/openssl-3.5.0.tar.gz | tar xz --strip-components=1 -C "$src" 2>/dev/null || true
    if [[ -f "$src/Configure" ]]; then
        ./Configure --prefix="$VENVDIR" --openssldir="$VENVDIR/ssl" \
                    -Wl,-rpath,"$VENVDIR/lib" \
                    no-ssl3 no-tests 2>&1
        make -j"$(nproc)" 2>&1
        make install_sw 2>&1
    else
        echo "  WARNING: openssl download failed"
    fi
    popd >/dev/null; echo "  openssl built."
fi

if ! command -v muchsync &>/dev/null; then
    echo "  Building muchsync from source ..."
    src="$BUILDDIR/muchsync"
    rm -rf "$src"; mkdir -p "$src"; pushd "$src" >/dev/null
    curl -sL https://www.muchsync.org/src/muchsync-7.tar.gz | tar xz --strip-components=1 -C "$src" 2>/dev/null || true
    if [[ -f "$src/configure" ]]; then
        ./configure --prefix="$VENVDIR" CXXFLAGS="-I$VENVDIR/include -I$VENVDIR/include/notmuch" \
                    LDFLAGS="-L$VENVDIR/lib -L$VENVDIR/lib64" 2>&1
        make -j"$(nproc)" 2>&1
        make install 2>&1
    else
        echo "  WARNING: muchsync download or configure not found"
    fi
    popd >/dev/null; echo "  muchsync built."
fi

# --- Python virtualenv ---
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

if ! python3 -m pip --version &>/dev/null; then
    echo "  Installing pip ..."
    curl -sL https://bootstrap.pypa.io/get-pip.py | python3
fi

echo "  Installing Python dependencies ..."
python3 -m pip install --quiet --upgrade pip
python3 -m pip install --quiet \
    PySide6 scikit-learn toml imapclient watchdog \
    mail-parser html2text beautifulsoup4

if ! python3 -c "import notmuch2" 2>/dev/null; then
    ns="$BUILDDIR/notmuch"
    if [[ -d "$ns/bindings/python-cffi" ]]; then
        echo "  Building notmuch2 Python bindings ..."
        pushd "$ns/bindings/python-cffi" >/dev/null
        python3 -m pip install --quiet . || true
        popd >/dev/null
    fi
fi

deactivate
echo "  Python virtualenv ready."

# --- Install scripts ---
echo "--- Installing scripts ---"
cp -P "$INSTALL_SRC"/scripts/*.py "$BINDIR/"
cp -P "$INSTALL_SRC"/scripts/*.jq "$BINDIR/" 2>/dev/null || true
for f in predict-tags decrypt-on-the-fly mbsync-and-decrypt; do
    cp -P "$INSTALL_SRC/scripts/$f" "$BINDIR/" 2>/dev/null || true
done
chmod +x "$BINDIR"/*.py "$BINDIR"/predict-tags "$BINDIR"/decrypt-on-the-fly "$BINDIR"/mbsync-and-decrypt 2>/dev/null || true

# Fix shebangs
sed -i "s|^python |${VENVDIR}/bin/python |" "$BINDIR/predict-tags" 2>/dev/null || true

echo "Creating wrapper scripts ..."
for name in ai-classify ai-train check-postponed edit-mail wait-for-change \
             view-mail view-thread open-drafts manage-mail \
             show-query-results send-mail get-message-id \
             pause-imap-sync config-helper-get-pixel-ratio \
             config-helper-get-dpi; do
    cat > "${BINDIR}/${name}" <<WRAP
#!/usr/bin/env bash
export TMPDIR="\${TMPDIR:-/tmp}"
export LD_LIBRARY_PATH="${VENVDIR}/lib:\${LD_LIBRARY_PATH:-}"
export PKG_CONFIG_PATH="${VENVDIR}/lib/pkgconfig:\${PKG_CONFIG_PATH:-}"
# Qt 6.5+ needs libxcb-cursor0 for xcb plugin. Fallback to wayland if missing.
if ! ldconfig -p 2>/dev/null | grep -q libxcb-cursor; then
    export QT_QPA_PLATFORM=wayland
fi
exec "${VENVDIR}/bin/python" "${BINDIR}/${name}.py" "\$@"
WRAP
    chmod +x "${BINDIR}/${name}"
done

# Symlink main binaries to BINDIR
for bin in notmuch mbsync msmtp muchsync; do
    if [[ -f "$VENVDIR/bin/$bin" ]]; then
        ln -sf "$VENVDIR/bin/$bin" "$BINDIR/$bin"
    fi
done

echo "  Scripts installed to $BINDIR"

# --- Desktop file ---
DESKTOP_SRC="${INSTALL_SRC}/kubux-mail-client.desktop"
if [[ -f "$DESKTOP_SRC" ]]; then
    sed -e "s|^Exec=show-query-results|Exec=${BINDIR}/show-query-results|" \
        -e "s|^Exec=manage-mail|Exec=${BINDIR}/manage-mail|" \
        "$DESKTOP_SRC" > "${APPDIR}/kubux-mail-client.desktop"
fi

# --- Icons ---
ICON_SRC="${INSTALL_SRC}/app-icon.png"
if [[ -f "$ICON_SRC" ]]; then
    mkdir -p "${ICONDIR}/256x256/apps"
    cp "$ICON_SRC" "${ICONDIR}/256x256/apps/kubux-mail-client.png"
fi

[[ -n "${TMPDIR:-}" ]] && rm -rf "$TMPDIR"

echo "============================================"
echo "Installation complete!"
echo "  Prefix: $PREFIX"
echo "  Binaries: $BINDIR"
echo "  Add to PATH: export PATH=\"\$PATH:${BINDIR}\""
echo "============================================"