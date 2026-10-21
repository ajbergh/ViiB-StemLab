"""PyInstaller entry; freeze_support must precede internal worker dispatch."""

from multiprocessing import freeze_support

from viib_stemlab.desktop_backend import main

if __name__ == "__main__":
    freeze_support()
    raise SystemExit(main())
