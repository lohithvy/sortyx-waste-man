#!/usr/bin/env python3
"""
Sortyx 2.0 — Hardware Connection Diagnostics CLI.

Run this script on the Raspberry Pi (or laptop) to diagnose:
- Host architecture and Raspberry Pi hardware model
- I2C bus status and PCA9685 servo driver responsiveness
- GPIO access permissions and ultrasonic sensor pins
- Camera interface availability
- Required configuration parameters
"""

import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from app.hardware.diagnostics import HardwareDiagnostics


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print("=" * 65)
    print("      SORTYX 2.0 -- HARDWARE CONNECTION & COMPATIBILITY CHECK")
    print("=" * 65)

    report = HardwareDiagnostics.run_full_diagnostics()

    print(f"\n[HOST PLATFORM]")
    print(f"  Raspberry Pi Hardware : {'YES (Target Hardware)' if report.is_raspberry_pi else 'NO (Development / Simulation)'}")
    print(f"  Detected Board Model  : {report.model_name}")
    print(f"  Architecture          : {report.architecture}")
    print(f"  Operating System      : {report.os_name}")
    print(f"  Python Runtime        : {report.python_version}")
    print(f"  Simulation Mode       : {'MANDATORY (Laptop / Simulated)' if report.simulation_mode_required else 'PHYSICAL HARDWARE READY'}")

    print(f"\n[SUBSYSTEM DIAGNOSTIC PROBES]")
    for item in report.subsystems:
        status_symbol = {
            "ok": "[OK]   ",
            "info": "[INFO] ",
            "warning": "[WARN] ",
            "error": "[ERROR]",
        }.get(item.status, "[INFO] ")

        print(f"  {status_symbol} {item.name}")
        print(f"           Details : {item.details}")
        if item.recommendation:
            print(f"           Action  : {item.recommendation}")
        print()

    print("=" * 65)
    if report.can_activate_physical_hardware:
        print("[OK] All Raspberry Pi hardware subsystems are detected and responsive.")
        print("     You may verify wiring before setting SIMULATION_MODE=false.")
        return 0
    else:
        print("[INFO] Hardware simulation mode active. Operating without physical actuation.")
        print("       To enable physical hardware, run on a Raspberry Pi 4 Model B with")
        print("       PCA9685 and ultrasonic sensors wired according to docs/HARDWARE_WIRING.md.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
