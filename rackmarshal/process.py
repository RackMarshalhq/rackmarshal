"""Bounded local child execution for finite operational stages (POSIX only).

A timed-out child and ordinary descendants in its new process group are killed.
This does not terminate a remote SSH job or a descendant that detaches into its
own session. Kernel-uninterruptible I/O is not a hard real-time guarantee.
"""
import math
import os
import signal
import subprocess

CREDENTIAL_TIMEOUT_SECONDS = 30
LOCAL_STAGE_TIMEOUT_SECONDS = 120
DEFAULT_STAGE_TIMEOUT_SECONDS = 300
_OWNER_PID = "_RACKMARSHAL_PROCESS_OWNER_PID"
_OWNER_SESSION = "_RACKMARSHAL_PROCESS_OWNER_SESSION"


def _managed_group():
    """Recognize our inherited new session, never the supervising session."""
    try:
        owner = int(os.environ.get(_OWNER_PID, ""))
        session = int(os.environ.get(_OWNER_SESSION, ""))
        if owner > 0 and session > 0 and owner != os.getpid():
            current_session = os.getsid(0)
            if (os.getsid(owner) == session and current_session != session
                    and os.getpgrp() == current_session):
                return os.getpgrp()
    except (ValueError, OverflowError, ProcessLookupError, PermissionError):
        pass
    return None


def stage_timeout():
    """Allow large operator-controlled inventories/backlogs a longer stage."""
    value = float(os.environ.get("RACKMARSHAL_STAGE_TIMEOUT_SECONDS", DEFAULT_STAGE_TIMEOUT_SECONDS))
    if not math.isfinite(value) or value <= 0:
        raise ValueError("RACKMARSHAL_STAGE_TIMEOUT_SECONDS must be finite and positive")
    return value


def run(command, *, timeout, input=None, capture_output=False, check=False, **kwargs):
    """A small subprocess.run subset with bounded process-group cleanup.

    Never returns partial stdout as a successful result after timeout. Each
    top-level invocation owns a new process group. Nested managed invocations
    share it: a nested timeout kills that stage group, including its supervisor,
    and the outer owner receives a nonzero exit rather than partial success.
    """
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("process timeout must be finite and positive")
    if input is not None:
        if "stdin" in kwargs:
            raise ValueError("stdin and input may not both be used")
        kwargs["stdin"] = subprocess.PIPE
    if capture_output:
        if "stdout" in kwargs or "stderr" in kwargs:
            raise ValueError("capture_output cannot be combined with stdout/stderr")
        kwargs["stdout"] = kwargs["stderr"] = subprocess.PIPE
    if "start_new_session" in kwargs or "process_group" in kwargs:
        raise ValueError("process group is managed by the timeout runner")
    group = _managed_group()
    supplied_environment = kwargs.pop("env", None)
    environment = dict(os.environ if supplied_environment is None else supplied_environment)
    environment[_OWNER_PID] = os.environ[_OWNER_PID] if group else str(os.getpid())
    environment[_OWNER_SESSION] = os.environ[_OWNER_SESSION] if group else str(os.getsid(0))
    process = subprocess.Popen(command, start_new_session=group is None, env=environment, **kwargs)
    group = group or process.pid
    try:
        stdout, stderr = process.communicate(input, timeout=timeout)
    except BaseException as exc:
        try:
            os.killpg(group, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            # A detached descendant can retain a pipe; never wait indefinitely.
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
        if isinstance(exc, subprocess.TimeoutExpired):
            # Commands and captured output can contain credentials/evidence.
            raise subprocess.TimeoutExpired("local command", timeout) from None
        raise
    result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    if check:
        result.check_returncode()
    return result
