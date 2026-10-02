#!/system/bin/sh
MODDIR=${0%/*}

# Enforce correct SELinux contexts for vendor overlays & daemons
chcon -R u:object_r:vendor_file:s0 "$MODDIR/vendor" 2>/dev/null
chcon -R u:object_r:vendor_file:s0 "$MODDIR/system/vendor" 2>/dev/null
chcon -R u:object_r:vendor_configs_file:s0 "$MODDIR/vendor/etc" 2>/dev/null
chcon -R u:object_r:vendor_configs_file:s0 "$MODDIR/system/vendor/etc" 2>/dev/null

# Dynamic bind-mount fallback for APatch / Magisk
if [ -f "$MODDIR/vendor/lib64/libimpl-ril.so" ]; then
    chcon u:object_r:vendor_file:s0 "$MODDIR/vendor/lib64/libimpl-ril.so" 2>/dev/null
    mount -o bind "$MODDIR/vendor/lib64/libimpl-ril.so" /vendor/lib64/libimpl-ril.so 2>/dev/null
    chcon u:object_r:vendor_file:s0 /vendor/lib64/libimpl-ril.so 2>/dev/null
fi

if [ -f "$MODDIR/vendor/etc/audio_route.xml" ]; then
    chcon u:object_r:vendor_configs_file:s0 "$MODDIR/vendor/etc/audio_route.xml" 2>/dev/null
    mount -o bind "$MODDIR/vendor/etc/audio_route.xml" /vendor/etc/audio_route.xml 2>/dev/null
    chcon u:object_r:vendor_configs_file:s0 /vendor/etc/audio_route.xml 2>/dev/null
fi

