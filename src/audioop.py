# Lightweight shim for the stdlib `audioop` on platforms where it's missing.
# Provide minimal functions used by third-party libraries for tests.


def max(slice, width):
    # Not used in tests; provide a no-op
    return 0


# Provide a fallback exception if functions are used incorrectly
class AudioOpError(Exception):
    pass
