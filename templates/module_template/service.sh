#!/system/bin/sh
MODDIR=${0%/*}

until [ "$(getprop sys.boot_completed)" = "1" ]; do
    sleep 1
done

# Ensure multi_sim_data_call and mobile_data1 are set
settings put global multi_sim_data_call 1 2>/dev/null
settings put global mobile_data1 1 2>/dev/null
settings put global mobile_data 1 2>/dev/null

MODULE_MD5=$(md5sum "$MODDIR/vendor/lib64/libimpl-ril.so" 2>/dev/null | awk '{print $1}')
CURRENT_MD5=$(md5sum /vendor/lib64/libimpl-ril.so 2>/dev/null | awk '{print $1}')
if [ -n "$MODULE_MD5" ] && [ "$CURRENT_MD5" != "$MODULE_MD5" ]; then
    mount -o bind "$MODDIR/vendor/lib64/libimpl-ril.so" /vendor/lib64/libimpl-ril.so 2>/dev/null
    setprop ctl.restart vendor.ril-daemon
fi
