#!/usr/bin/env python3
"""Run the CEF startup/shutdown regression harness in disposable OBS profiles."""
import argparse
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPLETED = "browser startup and immediate shutdown completed"
REJECTED = "task rejected safely before CEF initialization"
FAILED = "CEF failed to initialize"

parser = argparse.ArgumentParser()
parser.add_argument("--executable", type=Path, default=ROOT / "build" / "cef-startup-test")
parser.add_argument("--module", type=Path, default=ROOT / "build" / "obs-browser.so")
parser.add_argument("--data", type=Path, default=ROOT / "data")
parser.add_argument("--output-dir", type=Path, required=True)
parser.add_argument("--repeat", type=int, default=2)
parser.add_argument("--timeout", type=float, default=60)
parser.add_argument("--cef-arg", action="append", default=[])
args = parser.parse_args()

if args.repeat < 1:
    raise SystemExit("--repeat must be positive")
output = args.output_dir.resolve()
output.mkdir(parents=True, exist_ok=True)


def read(path):
    try:
        return path.read_text(errors="replace")
    except FileNotFoundError:
        return ""


def fresh_config(name):
    path = output / name
    try:
        path.mkdir()
    except FileExistsError:
        raise SystemExit(f"refusing to reuse profile {path}; use a fresh --output-dir")
    return path


def command(config, mode):
    return [str(args.executable.resolve()), str(args.module.resolve()), str(args.data.resolve()),
            str(config), mode, "--password-store=basic", *args.cef_arg]


def wait_for(process, log_path, marker, label):
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        if marker in read(log_path):
            return
        code = process.poll()
        if code is not None:
            raise RuntimeError(f"{label}: exited {code} before '{marker}'; see {log_path}")
        time.sleep(0.05)
    raise RuntimeError(f"{label}: timed out waiting for '{marker}'; see {log_path}")


def release(process):
    if process.stdin is None or process.stdin.closed:
        return
    try:
        process.stdin.write("\n")
        process.stdin.flush()
        process.stdin.close()
    except (BrokenPipeError, OSError):
        pass


def wait_process(process, log_path, label):
    try:
        code = process.wait(timeout=args.timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
        raise RuntimeError(f"{label}: did not exit after stdin release; see {log_path}")
    if code:
        raise RuntimeError(f"{label}: exited {code}; see {log_path}")


def stop(process):
    if process.poll() is None:
        process.kill()
        process.wait(timeout=5)
    if process.stdin and not process.stdin.closed:
        try:
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass


def run_mode(mode, marker, iteration):
    config = fresh_config(f"{mode}-{iteration}-config")
    log_path = output / f"{mode}-{iteration}.log"
    with log_path.open("w") as log:
        try:
            result = subprocess.run(command(config, mode), stdout=log, stderr=subprocess.STDOUT,
                                    timeout=args.timeout)
        except subprocess.TimeoutExpired:
            raise SystemExit(f"{mode} {iteration}: timed out after {args.timeout}s; see {log_path}")
    text = read(log_path)
    if result.returncode:
        raise SystemExit(f"{mode} {iteration}: exit {result.returncode}; see {log_path}")
    if marker not in text or COMPLETED not in text:
        raise SystemExit(f"{mode} {iteration}: missing completion evidence; see {log_path}")
    print(f"{mode} {iteration}: ok")


def run_hold(iteration):
    config = fresh_config(f"hold-{iteration}-config")
    holder_log = output / f"hold-{iteration}-holder.log"
    failure_log = output / f"hold-{iteration}-failure.log"
    holder = failure = None
    holder_file = failure_file = None
    try:
        holder_file = holder_log.open("w")
        holder = subprocess.Popen(command(config, "hold"), stdin=subprocess.PIPE,
                                  stdout=holder_file, stderr=subprocess.STDOUT, text=True)
        wait_for(holder, holder_log, "READY", "profile holder")

        failure_file = failure_log.open("w")
        failure = subprocess.Popen(command(config, "hold"), stdin=subprocess.PIPE,
                                   stdout=failure_file, stderr=subprocess.STDOUT, text=True)
        wait_for(failure, failure_log, FAILED, "locked-profile process")
        release(failure)
        wait_process(failure, failure_log, "locked-profile process")
        if COMPLETED not in read(failure_log):
            raise RuntimeError(f"locked-profile process: missing shutdown evidence; see {failure_log}")

        release(holder)
        wait_process(holder, holder_log, "profile holder")
        if COMPLETED not in read(holder_log):
            raise RuntimeError(f"profile holder: missing shutdown evidence; see {holder_log}")
        print(f"hold {iteration}: ok")
    finally:
        if failure is not None:
            stop(failure)
        if holder is not None:
            stop(holder)
        if failure_file is not None:
            failure_file.close()
        if holder_file is not None:
            holder_file.close()


try:
    for iteration in range(1, args.repeat + 1):
        run_mode("preinit", REJECTED, iteration)
        run_mode("initialize", COMPLETED, iteration)
        run_mode("source", COMPLETED, iteration)
        run_hold(iteration)
except RuntimeError as error:
    raise SystemExit(str(error)) from error
