class GitLabAPIError(Exception):
    """Raised when the GitLab API returns an unexpected error response."""

    def __init__(self, message: str, status_code: int | None = None, response_body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class TokenNotFoundError(Exception):
    """Raised when a named project access token cannot be found."""
