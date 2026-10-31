"""systemd ExecStopPost: make a timeout, kill or crash permanently visible as STOP.json."""
import json
import os
from pathlib import Path
import sys
import time

work = Path(sys.argv[1])
stop = work / "STOP.json"
if os.environ.get("SERVICE_RESULT") != "success" and not stop.exists():
    record = {"result": "FAIL_STOP", "service_result": os.environ.get("SERVICE_RESULT"),
              "exit_code": os.environ.get("EXIT_CODE"), "exit_status": os.environ.get("EXIT_STATUS"),
              "at_ns": time.time_ns()}
    with stop.open("x") as handle:
        json.dump(record, handle)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    fd = os.open(work, os.O_RDONLY | os.O_DIRECTORY)
    os.fsync(fd)
    os.close(fd)
