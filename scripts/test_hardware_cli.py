#!/usr/bin/env python3
"""
Sortyx 2.0 — Interactive Hardware Test & Calibration CLI.

SAFETY RULES:
1. Refuses to activate channels or pins marked NOT_CONFIGURED (-1).
2. Prompts user confirmation before each movement.
3. Automatically respects configured angles and rate limits.
4. Allows interactive empty and full calibration of ultrasonic sensors.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from app.core.config import get_settings
from app.models.enums import BinId
from app.schemas.hardware import HardwareConfig
from app.services.servo_service import ServoService
from app.services.ultrasonic_service import UltrasonicService


async def test_servos_menu(servo_svc: ServoService) -> None:
    print("\n--- SERVO MOTOR TEST MENU ---")
    print("1. Test Bio Servo Lid")
    print("2. Test Organic Servo Lid")
    print("3. Test Non-Bio Servo Lid")
    print("4. Emergency Stop (Close all bins)")
    print("0. Back to Main Menu")

    choice = input("Select an option: ").strip()
    bin_map = {"1": BinId.BIO, "2": BinId.ORGANIC, "3": BinId.NON_BIO}

    if choice in bin_map:
        target_bin = bin_map[choice]
        cfg = servo_svc._get_bin_config(target_bin)
        print(f"\nTarget: {target_bin.value.upper()} (Channel: {cfg.channel}, Open: {cfg.open_angle}°, Close: {cfg.close_angle}°)")

        if not cfg.is_configured and not servo_svc.simulation_mode:
            print(f"⚠️ Channel for '{target_bin.value}' is NOT_CONFIGURED (-1). Movement refused.")
            return

        confirm = input(f"Confirm opening {target_bin.value} lid for 5 seconds? (type 'yes' to proceed): ").strip()
        if confirm.lower() != "yes":
            print("Action cancelled by user.")
            return

        print(f"Opening {target_bin.value} lid...")
        await servo_svc.open_bin(target_bin, timeout_seconds=5.0)
        print("Lid open. Waiting 5 seconds before closing...")
        await asyncio.sleep(5.0)
        print(f"Closing {target_bin.value} lid...")
        await servo_svc.close_bin(target_bin)
        print("Lid closed and PWM signal released.")

    elif choice == "4":
        await servo_svc.close_all_bins()
        print("Emergency stop executed. All lids commanded closed.")


def test_ultrasonic_menu(ultra_svc: UltrasonicService) -> None:
    print("\n--- ULTRASONIC SENSOR TEST & CALIBRATION ---")
    print("1. Read all sensors (live distance & fill %)")
    print("2. Calibrate Empty Bin Distance")
    print("3. Calibrate Full Bin Distance")
    print("0. Back to Main Menu")

    choice = input("Select an option: ").strip()

    if choice == "1":
        print("\n--- LIVE SENSOR READINGS ---")
        for b in BinId:
            fill_pct, dist, status = ultra_svc.get_bin_fill_status(b)
            dist_str = f"{dist:.1f} cm" if dist is not None else "None (Unconfigured or Simulation)"
            print(f"  {b.value.upper():<10}: Distance = {dist_str:<30} Fill = {fill_pct:.1f}% Status = {status.value}")

    elif choice in ("2", "3"):
        is_empty = (choice == "2")
        state_label = "EMPTY" if is_empty else "FULL"
        print(f"\nSelect bin to calibrate as {state_label}:")
        print("1. Bio")
        print("2. Organic")
        print("3. Non-Bio")
        b_choice = input("Select bin: ").strip()
        bin_map = {"1": BinId.BIO, "2": BinId.ORGANIC, "3": BinId.NON_BIO}
        if b_choice in bin_map:
            target_bin = bin_map[b_choice]
            print(f"Ensure the {target_bin.value} bin is completely {state_label}.")
            confirm = input("Press ENTER when ready to take 10 calibration samples...")
            if is_empty:
                val = ultra_svc.calibrate_empty(target_bin, samples=10)
            else:
                val = ultra_svc.calibrate_full(target_bin, samples=10)

            if val is not None:
                print(f"✓ Calibration successful! {state_label} distance set to {val:.1f} cm.")
                print("  Update config/hardware.yaml with this calibrated value.")
            else:
                print(f"✗ Calibration failed. Verify sensor pins and connections.")


async def async_main() -> None:
    settings = get_settings()
    hw_config = HardwareConfig.load_from_yaml()

    servo_svc = ServoService(config=hw_config, simulation_mode=settings.app.simulation_mode)
    ultra_svc = UltrasonicService(config=hw_config, simulation_mode=settings.app.simulation_mode)

    while True:
        print("\n" + "=" * 55)
        print("     SORTYX 2.0 — HARDWARE TEST & CALIBRATION CLI")
        print("=" * 55)
        print(f"  Mode: {'SIMULATION (Physical actuation disabled)' if settings.app.simulation_mode else 'PHYSICAL HARDWARE ACTIVE'}")
        print("  1. Servo Motors Test (Lid Open / Close)")
        print("  2. Ultrasonic Sensors Test & Calibration")
        print("  3. Emergency Stop (Close all bins)")
        print("  0. Exit")

        choice = input("\nEnter choice [0-3]: ").strip()
        if choice == "1":
            await test_servos_menu(servo_svc)
        elif choice == "2":
            test_ultrasonic_menu(ultra_svc)
        elif choice == "3":
            await servo_svc.close_all_bins()
            print("All bin lids closed.")
        elif choice == "0":
            print("Exiting.")
            break
        else:
            print("Invalid option.")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\nAborted by user.")


if __name__ == "__main__":
    main()
