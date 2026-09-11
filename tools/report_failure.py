import os
import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def main():
    log_file = "test-output.log"
    if not os.path.exists(log_file):
        return
    with open(log_file, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()[-80:]
    content = "".join(lines)
    escaped = content.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::error title=Test Failure Traceback::{escaped}")

if __name__ == "__main__":
    main()
