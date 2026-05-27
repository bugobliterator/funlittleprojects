"""Command-line interface for the scanner tool."""

import click


@click.group()
def main() -> None:
    """Send Honeywell N36XX barcode commands over serial."""


if __name__ == "__main__":
    main()
