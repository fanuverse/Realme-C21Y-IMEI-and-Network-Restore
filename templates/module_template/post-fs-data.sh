#!/system/bin/sh
MODDIR=${0%/*}

# Dynamic bind-mount fallback for APatch / Magisk
if [ -f "$MODDIR/vendor/lib64/libimpl-ril.so" ]; then
    mount -o bind "$MODDIR/vendor/lib64/libimpl-ril.so" /vendor/lib64/libimpl-ril.so 2>/dev/null
fi
