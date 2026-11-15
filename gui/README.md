# kof95_cart_gui

Source of the builder window (Rust, [egui](https://github.com/emilk/egui)). It runs `kof95_cart.py` with the PyPy
found next to it (`pypy/`), with `KOF95_PROGRESS=1`, and shows its progress.

    cargo build --release                                            # this system
    cargo build --release --target x86_64-pc-windows-gnu             # Windows, from Linux (mingw-w64)
    cargo zigbuild --release --target x86_64-unknown-linux-gnu.2.31  # Linux, for glibc 2.31 and later (zig)

For a test without the release layout: `KOF95_PYTHON=/path/to/pypy3 KOF95_SCRIPT=/path/to/kof95_cart.py`.
