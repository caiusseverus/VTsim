# VTsim anchor package for custom_components.
#
# This __init__.py makes custom_components a regular Python package rooted at
# the VTsim project directory.  conftest.py relies on this so it can manipulate
# custom_components.__path__ to inject a versioned VT directory when
# VTSIM_VT_DIR is set, ensuring the correct version of
# custom_components.versatile_thermostat is imported regardless of sys.path
# search order.
