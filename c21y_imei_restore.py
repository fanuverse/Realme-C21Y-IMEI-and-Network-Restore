#!/usr/bin/env python3
"""
=============================================================================
 Realme C21Y (RMX3261 / RMX3263 - Unisoc T610 / UMS512)
 All-in-One Community Factory IMEI & Cellular Restoration Utility
=============================================================================
 Restores original factory IMEI 1 & IMEI 2, cellular voice calling, USSD,
 and mobile data after NVRAM wipe or corrupted flash on Generic System Images
 (Android 11, 12, 13, 14, 15, 16+) without external hardware dongles/boxes.
=============================================================================
"""

import os
import sys
import struct
import shutil
import zipfile
import hashlib
import argparse
import subprocess
from datetime import datetime

# ANSI Colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(SCRIPT_DIR, "templates")

def print_banner():
    print(f"""{BLUE}{BOLD}
=============================================================================
  Realme C21Y (Unisoc Tiger T610 / UMS512) Factory IMEI Restoration Tool
  Author: fanuverse | Native Repair Pipeline
=============================================================================
  Target: Realme C21Y (RMX3261, RMX3263), Android 11 / 12 / 13 / 14 / 15 / 16
  Hardware: Unisoc UMS512 (Tiger T610) Baseband CP RTOS + Userspace RIL
============================================================================={RESET}
""")

def luhn_checksum_valid(imei_str: str) -> bool:
    """Validates the 15th Luhn checksum digit of an IMEI string."""
    digits = [int(c) for c in imei_str]
    total = 0
    for i in range(14):
        d = digits[i]
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d = (d // 10) + (d % 10)
        total += d
    check_digit = (10 - (total % 10)) % 10
    return check_digit == digits[14]

def validate_imei(imei_str: str, label: str = "IMEI") -> bool:
    """Validates length, character set, and Luhn checksum."""
    if len(imei_str) != 15:
        print(f"{RED}[-] Error: {label} must be exactly 15 digits (got {len(imei_str)}).{RESET}")
        return False
    if not imei_str.isdigit():
        print(f"{RED}[-] Error: {label} must contain only decimal digits.{RESET}")
        return False
    if not luhn_checksum_valid(imei_str):
        print(f"{YELLOW}[!] Warning: {label} ({imei_str}) fails standard Luhn algorithm check.{RESET}")
        print(f"{YELLOW}    Double check the label on your retail box to ensure accuracy.{RESET}")
    return True

def encode_bcd_imei(imei_str: str) -> bytes:
    """Encodes a 15-digit IMEI numeric string into 8-byte 3GPP BCD Unisoc format."""
    digits = [int(c) for c in imei_str]
    # Byte 0: low nibble is 0x0A (or 0x08), high nibble is digit 0
    b0 = (digits[0] << 4) | 0x0a
    raw = [b0]
    for i in range(1, 15, 2):
        d1 = digits[i]
        d2 = digits[i+1]
        raw.append((d2 << 4) | d1)
    return bytes(raw)

def calc_unisoc_checksum(data: bytes) -> int:
    """Calculates standard Spreadtrum/Unisoc 16-bit one's complement checksum."""
    chkSum = 0
    l = len(data)
    idx = 0
    while l > 1:
        num = data[idx] | (data[idx+1] << 8)
        chkSum += num
        idx += 2
        l -= 2
    if l:
        chkSum += data[idx]
    chkSum = (chkSum >> 16) + (chkSum & 0xffff)
    chkSum += (chkSum >> 16)
    return (~chkSum) & 0xffff

def generate_clean_fixnv(template_path: str, imei1: str, imei2: str) -> bytes:
    """Generates a clean l_fixnv partition image with injected IMEIs and valid CRC."""
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"FixNV template not found at {template_path}")
    
    with open(template_path, "rb") as f:
        data = bytearray(f.read())
    
    if len(data) != 2097152:
        raise ValueError(f"Unexpected FixNV template size: {len(data)} (expected 2,097,152 bytes)")
    
    # Read Header
    hdr = data[:512]
    magic, length, old_crc, ver = struct.unpack('<IIII', hdr[:16])
    if magic != 0x00004e56:
        raise ValueError(f"Invalid FixNV magic 0x{magic:08x} (expected 0x00004e56)")
    
    body = data[512:512+length]
    offset = 4
    found_imei1 = False
    found_imei2 = False
    
    bcd_imei1 = encode_bcd_imei(imei1)
    bcd_imei2 = encode_bcd_imei(imei2)
    
    while offset < len(body) - 4:
        item_id, item_size = struct.unpack('<HH', body[offset:offset+4])
        if item_id == 0xffff:
            break
        if item_id == 0x0005:
            # Replace Item 5 (IMEI 1)
            body[offset+4:offset+4+8] = bcd_imei1
            found_imei1 = True
        elif item_id in [0x0179, 0x0186]:
            # Replace Item 0x179 and Item 0x186 (IMEI 2)
            body[offset+4:offset+4+8] = bcd_imei2
            found_imei2 = True
            
        offset += 4 + item_size
        offset = (offset + 3) & ~3
        
    if not (found_imei1 and found_imei2):
        raise ValueError(f"Could not locate Item 5 (found={found_imei1}) or Item 0x179 (found={found_imei2}) in template!")
    
    # Recalculate checksum
    new_crc = calc_unisoc_checksum(body)
    # Write updated body and header back to data
    data[512:512+length] = body
    struct.pack_into('<I', data, 8, new_crc)
    
    print(f"{GREEN}  [+] FixNV generated: IMEI 1={imei1}, IMEI 2={imei2}, Unisoc CRC=0x{new_crc:04x}{RESET}")
    return bytes(data)

def patch_modem_firmware(template_path: str, imei1: str, imei2: str) -> bytes:
    """Applies the 5-point machine code and default table patches to l_modem binary."""
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Modem template not found at {template_path}")
        
    with open(template_path, "rb") as f:
        data = bytearray(f.read())
        
    if len(data) != 26214400:
        raise ValueError(f"Unexpected modem template size: {len(data)} (expected 26,214,400 bytes)")
        
    # Patch 1: sp_a_imei_process (offset 0x010a981a) -> movs r0, #1; bx lr
    patch1_off = 0x010a981a
    data[patch1_off:patch1_off+4] = b'\x01\x20\x70\x47'
    
    # Patch 2: efuse security check (offset 0x10aa47c) -> *r0 = 0; return 1;
    patch2_off = 0x10aa47c
    data[patch2_off:patch2_off+8] = b'\x00\x21\x01\x60\x01\x20\x70\x47'
    
    # Patch 3: SIMLOCK memcmp bypass (offset 0x723b66) -> b #0x723b7a
    patch3_off = 0x723b66
    data[patch3_off:patch3_off+2] = b'\x08\xe0'
    
    # Patch 4: Default IMEI 1 in ROM table (offset 0x1462dcc)
    patch4_off = 0x1462dcc
    data[patch4_off:patch4_off+15] = imei1.encode('ascii')
    
    # Patch 5: Default IMEI 2 in ROM table (offset 0x1462ddb)
    patch5_off = 0x1462ddb
    data[patch5_off:patch5_off+15] = imei2.encode('ascii')
    
    md5 = hashlib.md5(data).hexdigest()
    print(f"{GREEN}  [+] Modem patched: Baseband CP RTOS bypasses active (MD5: {md5}){RESET}")
    return bytes(data)

def patch_ril_library(template_path: str, imei1: str, imei2: str) -> bytes:
    """Patches libimpl-ril.so userspace RIL hook to supply authentic IMEIs to Android framework."""
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"RIL template not found at {template_path}")
        
    with open(template_path, "rb") as f:
        data = bytearray(f.read())
        
    if len(data) != 352312:
        raise ValueError(f"Unexpected RIL template size: {len(data)} (expected 352,312 bytes)")
        
    # Hook call site at 0x23b48 -> branch to 0x48ee8
    # Assembly: b #0x48ee8 (offset: 0x48ee8 - 0x23b48 = 0x253a0 -> imm26: 0x94eb)
    data[0x23b48:0x23b48+8] = bytes.fromhex("d79e1210f752348b") # or standard branch hook
    
    # Hook payload at 0x48ee8
    payload = bytearray.fromhex(
        "74000035a2010010020014e20100104900d029d944f92901"
        "35f9e00313aae1031f2a03028052a0023fd61c0300141f20"
        "03d5"
    )
    data[0x48ee8:0x48ee8+len(payload)] = payload
    
    # Inject ASCII IMEI 1 (16 bytes null-padded) at 0x48f20
    imei1_bytes = imei1.encode('ascii').ljust(16, b'\x00')
    data[0x48f20:0x48f20+16] = imei1_bytes
    
    # Inject ASCII IMEI 2 (16 bytes null-padded) at 0x48f30
    imei2_bytes = imei2.encode('ascii').ljust(16, b'\x00')
    data[0x48f30:0x48f30+16] = imei2_bytes
    
    # Secondary branch at 0x49818
    data[0x49818:0x49818+8] = bytes.fromhex("44b8ff108450348b")
    
    md5 = hashlib.md5(data).hexdigest()
    print(f"{GREEN}  [+] Userspace RIL patched: libimpl-ril.so hook ready (MD5: {md5}){RESET}")
    return bytes(data)

def package_apatch_module(output_zip: str, patched_ril: bytes, module_template_dir: str):
    """Builds a flashable APatch/Magisk module zip containing the patched RIL binary and audio route fix."""
    with zipfile.ZipFile(output_zip, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        # Copy skeleton files
        for fname in ["customize.sh", "post-fs-data.sh", "service.sh", "module.prop"]:
            src = os.path.join(module_template_dir, fname)
            if os.path.exists(src):
                z.write(src, arcname=fname)
        # Copy META-INF
        meta_inf_dir = os.path.join(module_template_dir, "META-INF")
        if os.path.exists(meta_inf_dir):
            for root, _, files in os.walk(meta_inf_dir):
                for f in files:
                    full_p = os.path.join(root, f)
                    rel_p = os.path.relpath(full_p, module_template_dir)
                    z.write(full_p, arcname=rel_p)
        # Copy extra template assets (e.g. vendor/etc/audio_route.xml, apns-conf.xml)
        for sub in ["vendor", "system", "product"]:
            sub_path = os.path.join(module_template_dir, sub)
            if os.path.exists(sub_path):
                for root, _, files in os.walk(sub_path):
                    for f in files:
                        full_p = os.path.join(root, f)
                        rel_p = os.path.relpath(full_p, module_template_dir)
                        if not rel_p.endswith("libimpl-ril.so"):
                            z.write(full_p, arcname=rel_p)
        # Write patched RIL binaries
        z.writestr("vendor/lib64/libimpl-ril.so", patched_ril)
        z.writestr("system/vendor/lib64/libimpl-ril.so", patched_ril)
        
    print(f"{GREEN}  [+] APatch / Magisk module built: {os.path.basename(output_zip)}{RESET}")

def run_adb_cmd(adb_bin: str, args: list, timeout: int = 15) -> str:
    cmd = [adb_bin] + args
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if res.returncode != 0:
        err = res.stderr.decode(errors='ignore').strip()
        raise RuntimeError(f"ADB command failed: {' '.join(cmd)}\nError: {err}")
    return res.stdout.decode(errors='ignore').strip()

def flash_to_device(adb_bin: str, output_dir: str):
    """Flashes patched modem and fixnv partitions via ADB root shell."""
    print(f"\n{BLUE}{BOLD}[*] Connecting to device via ADB...{RESET}")
    devs = run_adb_cmd(adb_bin, ["devices"]).splitlines()
    active_devs = [l.split()[0] for l in devs if "\tdevice" in l]
    if not active_devs:
        raise RuntimeError("No device connected in 'device' mode! Enable USB debugging and authorize PC.")
    
    device_id = active_devs[0]
    print(f"{GREEN}[+] Detected device: {device_id}{RESET}")
    
    # Check root
    root_check = run_adb_cmd(adb_bin, ["shell", "su -c 'id -u'"])
    if root_check != "0":
        raise RuntimeError("Root (su) permission denied on device! Grant root access in APatch/Magisk.")
    print(f"{GREEN}[+] Root access verified (UID 0).{RESET}")

    # Dynamically find the correct partition directory for this ROM
    detect_path_cmd = (
        "if [ -d /dev/block/bootdevice/by-name ]; then "
        "echo /dev/block/bootdevice/by-name; "
        "elif [ -d /dev/block/by-name ]; then "
        "echo /dev/block/by-name; "
        "else "
        "find /dev/block -name by-name 2>/dev/null | head -n 1; "
        "fi"
    )
    by_name = run_adb_cmd(adb_bin, ["shell", f"su -c '{detect_path_cmd}'"]).strip()
    if not by_name:
        raise RuntimeError("Could not find a valid partition 'by-name' directory on device!")
    print(f"{GREEN}[+] Detected partition directory: {by_name}{RESET}")
    
    # 1. Back up existing partitions
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = f"/sdcard/imei_backup_{timestamp}"
    print(f"{YELLOW}[*] Backing up current NVRAM & modem partitions to {backup_dir}...{RESET}")
    run_adb_cmd(adb_bin, ["shell", f"su -c 'mkdir -p {backup_dir} && "
                                  f"dd if={by_name}/l_fixnv1_a of={backup_dir}/l_fixnv1_a.bin bs=1M && "
                                  f"dd if={by_name}/l_modem_a of={backup_dir}/l_modem_a.bin bs=1M'"])
    print(f"{GREEN}[+] Backup completed safely on device storage.{RESET}")
    
    # 2. Push patched files to device
    print(f"{YELLOW}[*] Uploading patched binaries to device /data/local/tmp/...{RESET}")
    run_adb_cmd(adb_bin, ["push", os.path.join(output_dir, "l_fixnv1.bin"), "/data/local/tmp/l_fixnv1.bin"])
    run_adb_cmd(adb_bin, ["push", os.path.join(output_dir, "l_modem_patched.bin"), "/data/local/tmp/l_modem_patched.bin"])
    run_adb_cmd(adb_bin, ["push", os.path.join(output_dir, "Realme-C21Y-IMEI-Restore.zip"), "/data/local/tmp/Realme-C21Y-IMEI-Restore.zip"])
    
    # 3. Flash partitions using the detected path
    print(f"{YELLOW}[*] Writing patched baseband modem & clean NVRAM to block partitions...{RESET}")
    flash_cmd = (
        "su -c '"
        f"dd if=/data/local/tmp/l_fixnv1.bin of={by_name}/l_fixnv1_a bs=1M && "
        f"dd if=/data/local/tmp/l_fixnv1.bin of={by_name}/l_fixnv1_b bs=1M && "
        f"dd if=/data/local/tmp/l_fixnv1.bin of={by_name}/l_fixnv2_a bs=1M && "
        f"dd if=/data/local/tmp/l_fixnv1.bin of={by_name}/l_fixnv2_b bs=1M && "
        f"dd if=/data/local/tmp/l_modem_patched.bin of={by_name}/l_modem_a bs=1M && "
        f"dd if=/data/local/tmp/l_modem_patched.bin of={by_name}/l_modem_b bs=1M && "
        f"dd if=/dev/zero of={by_name}/l_runtimenv1 bs=1M count=2 2>/dev/null; "
        f"dd if=/dev/zero of={by_name}/l_runtimenv2 bs=1M count=2 2>/dev/null; "
        "mkdir -p /data/adb/modules/realme_c21y_imei_restore/vendor/lib64 && "
        "mkdir -p /data/adb/modules/realme_c21y_imei_restore/system/vendor/lib64 && "
        "unzip -o /data/local/tmp/Realme-C21Y-IMEI-Restore.zip -d /data/adb/modules/realme_c21y_imei_restore && "
        "chmod -R 755 /data/adb/modules/realme_c21y_imei_restore && "
        "chcon -R u:object_r:vendor_file:s0 /data/adb/modules/realme_c21y_imei_restore && "
        "chcon -R u:object_r:vendor_configs_file:s0 /data/adb/modules/realme_c21y_imei_restore/vendor/etc 2>/dev/null; "
        "chcon -R u:object_r:vendor_configs_file:s0 /data/adb/modules/realme_c21y_imei_restore/system/vendor/etc 2>/dev/null; "
        "content update --uri content://telephony/carriers --bind protocol:s:IP --bind roaming_protocol:s:IP --bind type:s:\"default,ia,supl,dun,hipri\" --where \"numeric=\\\"63601\\\"\" 2>/dev/null; "
        "content update --uri content://telephony/carriers --bind protocol:s:IP --bind roaming_protocol:s:IP --bind type:s:\"default,ia,supl,dun,hipri\" --where \"numeric=\\\"63602\\\"\" 2>/dev/null; "
        "settings put global mobile_data_always_on 1 2>/dev/null; "
        "settings put global data_stall_recovery_on_bad_network 1 2>/dev/null; "
        "settings put global restricted_networking_mode 0 2>/dev/null; "
        "setprop persist.vendor.radio.fd.disable 1 2>/dev/null; "
        "sync'"
    )
    run_adb_cmd(adb_bin, ["shell", flash_cmd])
    print(f"{GREEN}{BOLD}[+] Flash operation completed successfully!{RESET}")
    
    # 4. Reboot confirmation
    ans = input(f"\n{BOLD}Would you like to reboot the device now to apply changes? [Y/n]: {RESET}").strip().lower()
    if ans in ["", "y", "yes"]:
        print(f"{YELLOW}[*] Rebooting device...{RESET}")
        try:
            run_adb_cmd(adb_bin, ["shell", "su -c 'reboot'"], timeout=5)
        except Exception:
            pass
        print(f"{GREEN}[+] Device reboot command sent. Wait ~30 seconds for full cellular initialization.{RESET}")

def main():
    print_banner()
    parser = argparse.ArgumentParser(description="Realme C21Y Factory IMEI & Cellular Restoration Tool")
    parser.add_argument("--imei1", type=str, help="15-digit original factory IMEI 1 (from box label)")
    parser.add_argument("--imei2", type=str, help="15-digit original factory IMEI 2 (from box label)")
    parser.add_argument("--output-dir", type=str, default="output", help="Directory to save generated files")
    parser.add_argument("--flash", action="store_true", help="Automatically flash generated files via ADB")
    parser.add_argument("--adb", type=str, default="adb", help="Path to ADB binary (default: 'adb')")
    parser.add_argument("--no-flash", action="store_true", help="Generate files only, do not flash to device")
    args = parser.parse_args()
    
    imei1 = args.imei1
    imei2 = args.imei2
    
    # Interactive input if not provided
    if not imei1:
        while True:
            try:
                imei1 = input(f"{BOLD}Enter Factory IMEI 1 (15 digits): {RESET}").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nAborted.")
                sys.exit(0)
            if validate_imei(imei1, "IMEI 1"):
                break
    else:
        if not validate_imei(imei1, "IMEI 1"):
            sys.exit(1)
            
    if not imei2:
        while True:
            try:
                imei2 = input(f"{BOLD}Enter Factory IMEI 2 (15 digits): {RESET}").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nAborted.")
                sys.exit(0)
            if validate_imei(imei2, "IMEI 2"):
                break
    else:
        if not validate_imei(imei2, "IMEI 2"):
            sys.exit(1)
            
    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"\n{BLUE}{BOLD}[*] Generating customized firmware packages for:{RESET}")
    print(f"    IMEI 1: {BOLD}{imei1}{RESET}")
    print(f"    IMEI 2: {BOLD}{imei2}{RESET}")
    print(f"    Output: {output_dir}\n")
    
    # 1. Generate FixNV
    fixnv_tmpl = os.path.join(TEMPLATES_DIR, "l_fixnv1_template.bin")
    fixnv_bytes = generate_clean_fixnv(fixnv_tmpl, imei1, imei2)
    fixnv_out = os.path.join(output_dir, "l_fixnv1.bin")
    with open(fixnv_out, "wb") as f:
        f.write(fixnv_bytes)
        
    # Duplicate to fixnv2
    fixnv2_out = os.path.join(output_dir, "l_fixnv2.bin")
    with open(fixnv2_out, "wb") as f:
        f.write(fixnv_bytes)
        
    # 2. Patch Modem
    modem_tmpl = os.path.join(TEMPLATES_DIR, "l_modem_template.bin")
    modem_bytes = patch_modem_firmware(modem_tmpl, imei1, imei2)
    modem_out = os.path.join(output_dir, "l_modem_patched.bin")
    with open(modem_out, "wb") as f:
        f.write(modem_bytes)
        
    # 3. Patch RIL
    ril_tmpl = os.path.join(TEMPLATES_DIR, "libimpl-ril64_template.so")
    ril_bytes = patch_ril_library(ril_tmpl, imei1, imei2)
    ril_out = os.path.join(output_dir, "libimpl-ril.so")
    with open(ril_out, "wb") as f:
        f.write(ril_bytes)
        
    # 4. Package Magisk / APatch Module
    module_tmpl_dir = os.path.join(TEMPLATES_DIR, "module_template")
    module_zip_out = os.path.join(output_dir, "Realme-C21Y-IMEI-Restore.zip")
    package_apatch_module(module_zip_out, ril_bytes, module_tmpl_dir)
    
    print(f"\n{GREEN}{BOLD}[✓] All files generated successfully in: {output_dir}{RESET}")
    print(f"    - l_fixnv1.bin / l_fixnv2.bin   (Clean calibrated NVRAM with injected IMEIs)")
    print(f"    - l_modem_patched.bin           (Baseband CP RTOS with bypass patches)")
    print(f"    - Realme-C21Y-IMEI-Restore.zip  (APatch / Magisk flashable module)")
    
    # Auto Flash or Instructions
    if args.no_flash:
        print_manual_instructions()
        return
        
    if args.flash:
        flash_to_device(args.adb, output_dir)
    else:
        try:
            ans = input(f"\n{BOLD}Do you want to flash these files to your connected phone now? [Y/n]: {RESET}").strip().lower()
            if ans in ["", "y", "yes"]:
                flash_to_device(args.adb, output_dir)
            else:
                print_manual_instructions()
        except (EOFError, KeyboardInterrupt):
            print_manual_instructions()

def print_manual_instructions():
    print(f"\n{YELLOW}{BOLD}Manual Flashing Instructions:{RESET}")
    print(f"  1. Boot phone into Android with Root (APatch or Magisk).")
    print(f"  2. Flash partitions via Root Shell / Termux / ADB:")
    print(f"     su")
    print(f"     dd if=l_fixnv1.bin of=/dev/block/bootdevice/by-name/l_fixnv1_a bs=1M")
    print(f"     dd if=l_fixnv1.bin of=/dev/block/bootdevice/by-name/l_fixnv1_b bs=1M")
    print(f"     dd if=l_fixnv1.bin of=/dev/block/bootdevice/by-name/l_fixnv2_a bs=1M")
    print(f"     dd if=l_fixnv1.bin of=/dev/block/bootdevice/by-name/l_fixnv2_b bs=1M")
    print(f"     dd if=l_modem_patched.bin of=/dev/block/bootdevice/by-name/l_modem_a bs=1M")
    print(f"     dd if=l_modem_patched.bin of=/dev/block/bootdevice/by-name/l_modem_b bs=1M")
    print(f"     dd if=/dev/zero of=/dev/block/bootdevice/by-name/l_runtimenv1 bs=1M count=2")
    print(f"     dd if=/dev/zero of=/dev/block/bootdevice/by-name/l_runtimenv2 bs=1M count=2")
    print(f"  3. Install Realme-C21Y-IMEI-Restore.zip in APatch / Magisk Manager.")
    print(f"  4. Reboot phone.")

if __name__ == "__main__":
    main()
