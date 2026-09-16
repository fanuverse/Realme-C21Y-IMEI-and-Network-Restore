# Realme C21Y (RMX3261 / RMX3263) Factory IMEI & Cellular Restoration Tool

> **Author**: [fanuverse](https://github.com/fanuverse)  
> **Native, 100% Software Solution for Unisoc Tiger T610 / UMS512 SoC**  
> *No Miracle Box, Pandora Box, or proprietary hardware dongles required.*

---

## 1. Background & Why This Exists

On the **Realme C21Y** (`RMX3261` and `RMX3263`), the baseband modem and radio calibration reside in Unisoc NVRAM partitions (`l_fixnv1`, `l_fixnv2`, `l_runtimenv1`, and `prodnv`). When a user wipes flash or loses their NVRAM backup, traditional IMEI repair tools fail because:

1. **Hardware Efuse Enforcement**: The Unisoc T610 baseband CP RTOS firmware checks efuse block `0x24` at boot (`0x10aa47c`). If secure boot is enabled, the modem rejects raw NVRAM Items (Item 5 for IMEI 1, Item 0x179 for IMEI 2) and demands 153-byte cryptographic signature tokens (`ENIMEI1_DATA` / `ENIMEI2_DATA`).
2. **CP Zero-Fallback**: When token verification fails, the baseband modem CP zeros its internal RAM buffer and transmits `000000000000000` to the cell tower during 3GPP NAS `IDENTITY REQUEST`.
3. **Carrier Rejection**: Cellular carriers (EIR) reject `000000000000000`, permanently locking the device into **Emergency Bearer Services Only** (`+CREG: 1,8`, `mIsEmergencyOnly=true`). Voice calling, USSD (`*804#`, `*123#`), and mobile data are completely blocked.
4. **Manufacturer Advice**: Manufacturers and repair shops instruct users to buy expensive hardware flashing boxes (Pandora Box or Miracle Box). 

**This utility solves the problem natively in software** by combining pristine stock RF calibrations, a patched baseband CP firmware, and a userspace RIL module.

---

## 2. Technical Architecture

This utility restores cellular service across all three architectural layers:

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Userspace RIL (Android Framework / Settings Display)      │
│    Patched libimpl-ril.so via APatch/Magisk module          │
├─────────────────────────────────────────────────────────────┤
│ 2. Baseband Modem CP RTOS (Over-The-Air Air Interface)       │
│    Patched l_modem:                                         │
│    - sp_a_imei_process (0x010a981a -> movs r0, #1; bx lr)  │
│    - Efuse state check (0x10aa47c -> *r0 = 0; return 1)     │
│    - SIMLOCK comparator bypass (0x723b66 -> b #0x723b7a)     │
│    - Default ROM table fallback (0x1462dcc -> Authentic IMEIs)│
├─────────────────────────────────────────────────────────────┤
│ 3. Calibrated NVRAM Partitions (Hardware RF Calibrations)    │
│    Clean l_fixnv1 / l_fixnv2 with intact factory RF tables   │
│    and valid Unisoc 16-bit one's complement checksums       │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Requirements

- **Device**: Realme C21Y (`RMX3261` or `RMX3263`).
- **Root Access**: APatch (recommended for Android 13/14/15/16 GSIs) or Magisk.
- **Original Factory IMEIs**: Printed on the original retail box or back sticker.
- **Host PC**: Linux, macOS, or Windows (WSL or native Python 3.7+).
- **ADB**: USB Debugging enabled in Developer Options.

---

## 4. Quick Start (Automatic via ADB)

### Step 1: Connect Device
Connect your Realme C21Y to your computer with USB Debugging enabled and authorized.

### Step 2: Run the Utility
```bash
python3 c21y_imei_restore.py
```

The tool will:
1. Prompt you to enter your authentic factory **IMEI 1** and **IMEI 2** from your box.
2. Validate format and Luhn checksum.
3. Generate customized `l_fixnv1.bin`, `l_fixnv2.bin`, and patched `l_modem_patched.bin`.
4. Automatically back up existing device partitions to `/sdcard/imei_backup_<timestamp>/`.
5. Flash the partitions directly to both slot A and slot B (`l_fixnv1_a/b`, `l_fixnv2_a/b`, `l_modem_a/b`).
6. Zero out runtime NVRAM (`l_runtimenv1`, `l_runtimenv2`) to force clean regeneration.
7. Install the userspace RIL module into APatch/Magisk.
8. Cleanly reboot your device.

---

## 5. Non-Interactive / CLI Usage

You can automate the generation and flashing via CLI flags:

```bash
# Automated generation and instant ADB flashing:
python3 c21y_imei_restore.py --imei1 <YOUR_IMEI_1> --imei2 <YOUR_IMEI_2> --flash

# Generate files only (for manual flashing or Termux):
python3 c21y_imei_restore.py --imei1 <YOUR_IMEI_1> --imei2 <YOUR_IMEI_2> --no-flash --output-dir ./my_output
```

---

## 6. Manual Flashing Instructions (On-Device via Termux / Root Shell)

If you generated the files on a PC and want to flash them manually on the phone (or via Termux):

1. Transfer `l_fixnv1.bin`, `l_modem_patched.bin`, and `Realme-C21Y-IMEI-Restore.zip` to your phone's storage (`/sdcard/`).
2. Open Termux or an ADB root shell:
   ```bash
   su
   # Flash clean calibrated NVRAM:
   dd if=/sdcard/l_fixnv1.bin of=/dev/block/bootdevice/by-name/l_fixnv1_a bs=1M
   dd if=/sdcard/l_fixnv1.bin of=/dev/block/bootdevice/by-name/l_fixnv1_b bs=1M
   dd if=/sdcard/l_fixnv1.bin of=/dev/block/bootdevice/by-name/l_fixnv2_a bs=1M
   dd if=/sdcard/l_fixnv1.bin of=/dev/block/bootdevice/by-name/l_fixnv2_b bs=1M

   # Flash patched baseband modem firmware:
   dd if=/sdcard/l_modem_patched.bin of=/dev/block/bootdevice/by-name/l_modem_a bs=1M
   dd if=/sdcard/l_modem_patched.bin of=/dev/block/bootdevice/by-name/l_modem_b bs=1M

   # Clear stale runtime NVRAM:
   dd if=/dev/zero of=/dev/block/bootdevice/by-name/l_runtimenv1 bs=1M count=2
   dd if=/dev/zero of=/dev/block/bootdevice/by-name/l_runtimenv2 bs=1M count=2
   sync
   ```
3. Open **APatch** or **Magisk** Manager on your phone.
4. Go to **Modules** -> **Install from storage** -> Select `Realme-C21Y-IMEI-Restore.zip`.
5. Reboot your device.

---

## 7. Verification

After reboot, verify cellular operation:

1. **Android Settings**: Go to **Settings** -> **About Phone**. Both IMEI 1 and IMEI 2 will display your factory numbers.
2. **Network Signal**: Both SIMs will show active signal bars (no 'X' or emergency indicators).
3. **Voice & USSD**: Open Phone dialer and dial your balance inquiry code (e.g. `*804#`, `*123#`) or make a test phone call.
4. **Mobile Data**: Turn off Wi-Fi; 4G/LTE mobile data will connect immediately with full internet access.

---

## 8. Disclaimer & Legal Notice

This tool is strictly intended for device repair and restoring authentic original factory IMEIs that were lost due to flash corruption or NVRAM erasure. Modifying mobile device identifiers to values other than the device's authentic factory numbers printed on its original label is strictly prohibited and may violate local laws.
