# Live Diagnostics — Python pyads Patterns

Principles / when to escalate: skill `twincat3-live-diagnostics` + rule
`twincat3-mcp-live-diagnostics`. Patterns below are **inline pseudocode** —
adapt to the open project; do not require an external sample repo.

## Minimal connect + R/W

```python
import os
import pyads

NET = os.environ.get("TWINCAT_UMRT_NET", "127.0.0.1.1.1")  # or from twincat_umrt_status
PORT = int(os.environ.get("TWINCAT_UMRT_PORT", "851"))

plc = pyads.Connection(NET, PORT)
plc.open()
try:
    en = plc.read_by_name("P_Sample.bEnable")
    plc.write_by_name("P_Sample.bEnable", True)
    vals = plc.read_list_by_name([
        "P_Sample.bEnable",
        "P_Sample.fbDevice._nStep",
    ])
finally:
    plc.close()
```

Get `NET` from `twincat_umrt_status` → `ams_net_id` when using MCP UmRT.

## Wait-until (poll)

```python
import time

def wait_until(plc, symbol: str, predicate, timeout_s: float = 5.0, dt: float = 0.05):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        v = plc.read_by_name(symbol)
        if predicate(v):
            return v
        time.sleep(dt)
    raise TimeoutError(f"{symbol} after {timeout_s}s")
```

Prefer **counter / state waits** over fixed long sleeps when the PLC exposes
progress (e.g. payload counters, step enums).

## Suite skeleton

```python
# tests/ads_live_suite.py  (project-local)
# - NET/PORT constants or env
# - path tables: PROG = "P_Sample"; DEVICE = f"{PROG}.fbDevice"
# - begin_suite / begin_phase / live_result helpers (optional progress log)
# - with RuntimeGuard(NET, PORT): ...  # abort if AdsState != RUN
# - write markdown report under tests/reports/
```

## Runtime watchdog (fatal abort)

Background thread: poll `plc.read_state()`; if not `ADSSTATE_RUN`, raise a
fatal error and stop the suite (do not continue other cases after pagefault /
STOP / INVALID). Exit code convention for orchestrators: non-zero fatal
(e.g. `99`) so a `run_all` wrapper does not start the next suite.

## Practical tips (from real online suites)

- Centralize NetId/port + path prefixes in one `common.py`-style module
- Batch with `read_list_by_name` / `write_list_by_name`
- Log ADS CMD/RSP only behind a `--debug` flag
- After writes that trigger ramps: sample with `time.sleep` sized from FB
  TIME params (+ slack); UmRT wall-clock is slower than RT targets
- On fatal ADS text (`device is not ready`, port closed, …) abort hard
- Restore inputs / disable automation flags in `finally` when possible

## Agent workflow for Python deep-dive

1. Confirm PLC already online (`ready_for_ads`) via MCP first
2. Ask where to put the script (or use a temp path the user names)
3. Write a **small** focused script (one scenario), not a mega-suite
4. Run it in the project venv / system Python with `pyads` installed
5. Summarize PASS/FAIL + key symbol values; attach report path if written
6. Do not commit scripts unless the user asks
