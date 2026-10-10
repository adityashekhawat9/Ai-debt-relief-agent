class AppException(Exception):
    """Base exception for the application."""
    def __init__(self, message: str, code: str, status_code: int = 500, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}

class ComplianceError(AppException):
    """Raised when a compliance check fails."""
    def __init__(self, message: str, code: str = "COMPLIANCE_ERROR", status_code: int = 403, details: dict | None = None):
        super().__init__(message, code, status_code, details)

class DNCError(ComplianceError):
    """Raised when lead is on Do Not Call list."""
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="DNC_BLOCKED", details=details)

class CallingHoursError(ComplianceError):
    """Raised when calling outside allowed hours."""
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="OUTSIDE_CALLING_HOURS", details=details)

class ConsentMissingError(ComplianceError):
    """Raised when lead consent is missing."""
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="CONSENT_MISSING", details=details)

class CallTimerExpiredError(AppException):
    """Raised when max call duration is reached."""
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="CALL_TIMER_EXPIRED", status_code=408, details=details)

class TransferError(AppException):
    """Raised when agent transfer fails."""
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="TRANSFER_FAILED", status_code=502, details=details)

class AIServiceError(AppException):
    """Base exception for AI service failures."""
    def __init__(self, message: str, code: str = "AI_SERVICE_ERROR", status_code: int = 503, details: dict | None = None):
        super().__init__(message, code, status_code, details)

class STTError(AIServiceError):
    """Raised when Speech-to-Text service fails."""
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="STT_FAILED", details=details)

class LLMError(AIServiceError):
    """Raised when Language Model service fails."""
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="LLM_FAILED", details=details)

class TTSError(AIServiceError):
    """Raised when Text-to-Speech service fails."""
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="TTS_FAILED", details=details)

class DatabaseError(AppException):
    """Raised when a database operation fails."""
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="DB_ERROR", status_code=500, details=details)

class RedisError(AppException):
    """Raised when a Redis operation fails."""
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="REDIS_ERROR", status_code=500, details=details)

class NotFoundError(AppException):
    """Raised when a requested resource is not found."""
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="NOT_FOUND", status_code=404, details=details)

class ValidationError(AppException):
    """Raised when data validation fails."""
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="VALIDATION_ERROR", status_code=422, details=details)

class AuthenticationError(AppException):
    """Raised when user authentication fails."""
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="AUTH_FAILED", status_code=401, details=details)

class AuthorizationError(AppException):
    """Raised when authenticated user lacks permissions."""
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="FORBIDDEN", status_code=403, details=details)
