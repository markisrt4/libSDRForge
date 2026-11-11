#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

if [[ -z "${PREFIX:-}" ]] ||
   [[ "$PREFIX" != /data/data/com.termux/* ]]; then
    echo "This script requires Termux."
    exit 1
fi

ROOT="$HOME/src/rtl-sdr"
PATCH_DIR="$(cd "$(dirname "$0")/.." && pwd)/patches"
PATCH="$PATCH_DIR/rtl-sdr-termux-usb-fd.patch"

pkg install -y \
    git clang cmake make pkg-config libusb

if [[ ! -d "$ROOT/.git" ]]; then
    git clone \
      https://github.com/osmocom/rtl-sdr.git \
      "$ROOT"
fi

cd "$ROOT"

if ! grep -q 'int rtlsdr_open_fd(' \
    src/librtlsdr.c; then
    git apply --check "$PATCH"
    git apply "$PATCH"
fi

cmake -S . -B build-termux \
    -DCMAKE_INSTALL_PREFIX="$PREFIX" \
    -DINSTALL_UDEV_RULES=OFF \
    -DDETACH_KERNEL_DRIVER=OFF

cmake --build build-termux \
    --target rtlsdr rtl_test rtl_tcp rtl_fm \
    -j 4

cp -L build-termux/src/librtlsdr.so \
    "$PREFIX/lib/librtlsdr.so.2.0.3"

python - <<'PY'
import ctypes
import os

path = os.path.join(
    os.environ["PREFIX"],
    "lib/librtlsdr.so"
)

lib = ctypes.CDLL(path)
assert hasattr(lib, "rtlsdr_open_fd")

print("Termux RTL-SDR FD support: PASS")
PY
