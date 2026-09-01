"""COM HRESULT constants and retry classification helpers."""

RPC_E_CALL_REJECTED = -2147418111   # 0x80010001 signed
RPC_E_CALL_CANCELED = -2147418110   # 0x80010002 signed
RPC_E_SERVERCALL_RETRYLATER = -2147418102  # 0x8001010A signed
RPC_E_DISCONNECTED = -2147417848    # 0x80010108 signed
RPC_E_CANTCALLOUT_ININPUTSYNCCALL = -2147417836  # 0x8001010D signed
RPC_S_SERVER_UNAVAILABLE = -2147023174  # 0x800706BA signed
E_ACCESSDENIED = -2147024891  # 0x80070005 signed

_QUIT_WAIT_S = 8
_QUIT_POLL_S = 0.3

_VS_BUILD_STATE_IN_PROGRESS = 2
_VS_BUILD_STATE_DONE = 3
_STABLE_OPEN_POLLS = 6
_STABLE_CLOSED_POLLS = 10

_BUSY_CALL_HRESULTS = {
    RPC_E_CALL_REJECTED,
    RPC_E_CALL_CANCELED,
    RPC_E_SERVERCALL_RETRYLATER,
    RPC_E_DISCONNECTED,
    RPC_E_CANTCALLOUT_ININPUTSYNCCALL,
}

_RETRYABLE_HRESULTS = {
    *_BUSY_CALL_HRESULTS,
    RPC_S_SERVER_UNAVAILABLE,
}


def is_call_rejected(exc: Exception) -> bool:
    if hasattr(exc, "hresult") and exc.hresult in _BUSY_CALL_HRESULTS:
        return True
    for arg in getattr(exc, "args", ()):
        if isinstance(arg, int) and arg in _BUSY_CALL_HRESULTS:
            return True
    return False


def is_retryable_com_error(exc: Exception) -> bool:
    if hasattr(exc, "hresult") and exc.hresult in _RETRYABLE_HRESULTS:
        return True
    for arg in getattr(exc, "args", ()):
        if isinstance(arg, int) and arg in _RETRYABLE_HRESULTS:
            return True
    return False


def is_access_denied(exc: Exception) -> bool:
    if hasattr(exc, "hresult") and exc.hresult == E_ACCESSDENIED:
        return True
    args = getattr(exc, "args", ())
    for arg in args:
        if isinstance(arg, int) and arg == E_ACCESSDENIED:
            return True
        if isinstance(arg, tuple) and len(arg) >= 6:
            if isinstance(arg[5], int) and arg[5] == E_ACCESSDENIED:
                return True
    return False
