class OasisAlpacaConfigError(Exception):
    """Raised when required configuration is missing or invalid."""
    pass


class OasisAlpacaError(Exception):
    """Raised when an error occurs during alpaca runtime."""
    pass
