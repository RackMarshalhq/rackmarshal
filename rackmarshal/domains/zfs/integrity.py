"""Permanent data errors are integrity evidence, not historical I/O counters."""


def integrity_state(error_count):
    if type(error_count) is not int or error_count < 0:
        return "UNKNOWN"
    return "CLEAN" if error_count == 0 else "PROBLEM"
