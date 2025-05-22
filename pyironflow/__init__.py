# Internal init
from ._version import get_versions

# Set version of pyiron_base
__version__ = get_versions()["version"]

try:
    from .pyironflow import PyironFlow
except FileNotFoundError:
    print("WARNING: could not import PyironFlow, likely because js sources "
          "are not build and we are in build env that just tries to get the "
          "version number.")
