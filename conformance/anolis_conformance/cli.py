"""Console entry point: ``anolis-adpp-conformance`` -> pytest over this package."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    import pytest

    # When installed, the pytest11 entry point auto-registers the plugin, so we
    # only point pytest at the package. (For an uninstalled checkout, run pytest
    # directly with `-p anolis_conformance.plugin`.)
    args = list(sys.argv[1:] if argv is None else argv)
    return pytest.main(["--pyargs", "anolis_conformance", *args])


if __name__ == "__main__":
    raise SystemExit(main())
