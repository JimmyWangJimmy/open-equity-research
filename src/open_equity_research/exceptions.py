class OpenEquityResearchError(Exception):
    """Base exception for user-facing failures."""


class ConfigurationError(OpenEquityResearchError):
    """Raised when required local configuration is invalid."""


class DataSourceError(OpenEquityResearchError):
    """Raised when a source cannot be fetched or parsed safely."""


class ValidationError(OpenEquityResearchError):
    """Raised when research artifacts fail an integrity check."""


class ValuationError(OpenEquityResearchError):
    """Raised when valuation inputs are invalid or unsafe."""
