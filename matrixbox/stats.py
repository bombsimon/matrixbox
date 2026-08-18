import gc
import os
import time

# There's no OS-level scheduler to ask for load — every loop (the kernel's
# and every app's) is a single cooperative while-loop with a fixed sleep at
# the end, so "CPU load" here is an EWMA of how much of each iteration was
# spent working vs sleeping — see docs/ARCHITECTURE.md. record_tick() must
# be called once per loop iteration, right after that iteration's sleep.
_SMOOTHING = 0.25
_load = 0.0
_last_tick = time.monotonic()


def record_tick(sleep_seconds: float):
    global _load, _last_tick

    now = time.monotonic()
    elapsed = now - _last_tick
    _last_tick = now
    if elapsed <= 0:
        return

    busy_fraction = max(0.0, min(1.0, (elapsed - sleep_seconds) / elapsed))
    _load += (busy_fraction - _load) * _SMOOTHING


def cpu_percent() -> int:
    return round(_load * 100)


def mem_bytes() -> tuple:
    # (used, total) — CircuitPython's heap, not the flash filesystem.
    free = gc.mem_free()
    alloc = gc.mem_alloc()

    return alloc, alloc + free


def mem_percent() -> int:
    used, total = mem_bytes()
    if total <= 0:
        return 0

    return round(used * 100 / total)


def flash_bytes() -> tuple:
    # (used, total) — the CIRCUITPY filesystem, where apps live.
    stat = os.statvfs("/")
    block_size, total_blocks, free_blocks = stat[0], stat[2], stat[3]
    total = block_size * total_blocks
    free = block_size * free_blocks

    return total - free, total
