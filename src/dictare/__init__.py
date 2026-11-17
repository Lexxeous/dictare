"""dictare: Voice-to-text for your terminal."""

import os as _os
import re as _re

__version__ = "0.7.0rc2"

# Keep the literal release version above readable by Hatch and installers.
# The checkout-local runner may display a unique, non-publishable dev label.
if _os.environ.get("DICTARE_DEV_MODE") == "1":
    _dev_version = _os.environ.get("DICTARE_DEV_VERSION", "")
    if _re.fullmatch(r"\d+\.\d+\.\d+\.dev\d+\+[a-z0-9.]+", _dev_version):
        __version__ = _dev_version

# URL prefix where the OpenVIP protocol endpoints are mounted.
# All OpenVIP routes live under this path (e.g. /openvip/status, /openvip/speech).
# Management (dictare-specific) routes live under /api/.
OPENVIP_BASE_PATH = "/openvip"
