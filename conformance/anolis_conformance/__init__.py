"""Cross-provider ADPP conformance harness.

Drives any ADPP provider binary through the ADPP v1 wire lifecycle and asserts
compliance. See ``ADPP-CONFORMANCE.md`` for the executable spec.

Run it against a provider binary:

    anolis-adpp-conformance \\
        --provider-bin ./build/.../anolis-provider-X \\
        --provider-config config/conformance.yaml \\
        --provider-profile conformance.toml

or equivalently (the plugin is not globally registered, so load it explicitly)::

    pytest -p anolis_conformance.plugin --pyargs anolis_conformance --provider-bin ...
"""

__all__ = ["AdppClient", "ProviderProfile", "load_profile"]

from .client import AdppClient
from .profiles import ProviderProfile, load_profile
