class LLMError(Exception):
    def __init__(self, message: str, status_code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


def classify_llm_error(exc: Exception) -> LLMError:
    if isinstance(exc, LLMError):
        return exc
    message = str(exc)
    lowered = message.lower()
    retryable = any(value in lowered for value in ["timeout", "timed out", "connection", "429", "500", "502", "503", "504"])
    status_code = None
    for code in [429, 500, 502, 503, 504, 401, 403, 404]:
        if str(code) in message:
            status_code = code
            break
    return LLMError(message, status_code=status_code, retryable=retryable)
