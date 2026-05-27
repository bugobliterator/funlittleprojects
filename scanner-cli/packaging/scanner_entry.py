"""PyInstaller entry point for the standalone single-folder build.

PyInstaller targets a script, not a console_scripts name, so this thin launcher
just invokes the CLI's main().
"""

from scanner.cli import main

if __name__ == "__main__":
    main()
