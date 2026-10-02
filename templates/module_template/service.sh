#!/system/bin/sh
MODDIR=${0%/*}

until [ "$(getprop sys.boot_completed)" = "1" ]; do
    sleep 1
done

# Enforce correct SELinux contexts for vendor overlays & daemons
chcon -R u:object_r:vendor_file:s0 "$MODDIR/vendor" 2>/dev/null
chcon -R u:object_r:vendor_file:s0 "$MODDIR/system/vendor" 2>/dev/null
chcon -R u:object_r:vendor_configs_file:s0 "$MODDIR/vendor/etc" 2>/dev/null
chcon -R u:object_r:vendor_configs_file:s0 "$MODDIR/system/vendor/etc" 2>/dev/null

# Ensure multi_sim_data_call and mobile_data1 are set
settings put global multi_sim_data_call 1 2>/dev/null
settings put global mobile_data1 1 2>/dev/null
settings put global mobile_data 1 2>/dev/null

# Cellular Mobility, Fast Dormancy & Data Stall Recovery
settings put global mobile_data_always_on 1 2>/dev/null
settings put global data_stall_recovery_on_bad_network 1 2>/dev/null
settings put global restricted_networking_mode 0 2>/dev/null

# Disable Unisoc modem fast dormancy (prevents dropping PDP context on idle/commute)
resetprop -n persist.vendor.radio.fd.disable 1 2>/dev/null
resetprop -n persist.vendor.radio.fastdormancy false 2>/dev/null
resetprop -n ro.telephony.default_network 9 2>/dev/null
resetprop -n telephony.lteOnCdmaDevice 0 2>/dev/null

# Fix Ethio Telecom & Safaricom APN in telephony provider:
# Enforces pure IPv4 protocol to prevent 4G IPv6 routing blackholes and adds 'ia' (Initial Attach)
# to prevent Packet Switched (PS) data detachment during cell tower mobility / handover.
content update --uri content://telephony/carriers \
    --bind protocol:s:IP \
    --bind roaming_protocol:s:IP \
    --bind type:s:"default,ia,supl,dun,hipri" \
    --where "numeric=\"63601\"" 2>/dev/null

content update --uri content://telephony/carriers \
    --bind protocol:s:IP \
    --bind roaming_protocol:s:IP \
    --bind type:s:"default,ia,supl,dun,hipri" \
    --where "numeric=\"63602\"" 2>/dev/null

# Audio & Cellular Coexistence Properties
resetprop -n persist.vendor.audio.routing 1 2>/dev/null
resetprop -n persist.vendor.audio.bt_route 1 2>/dev/null
resetprop -n persist.vendor.bt.coex.enable 1 2>/dev/null
resetprop -n persist.vendor.wifi.bt.coex 1 2>/dev/null

# Fallback bind-mount for libimpl-ril.so
MODULE_MD5=$(md5sum "$MODDIR/vendor/lib64/libimpl-ril.so" 2>/dev/null | awk '{print $1}')
CURRENT_MD5=$(md5sum /vendor/lib64/libimpl-ril.so 2>/dev/null | awk '{print $1}')
if [ -n "$MODULE_MD5" ] && [ "$CURRENT_MD5" != "$MODULE_MD5" ]; then
    chcon u:object_r:vendor_file:s0 "$MODDIR/vendor/lib64/libimpl-ril.so" 2>/dev/null
    mount -o bind "$MODDIR/vendor/lib64/libimpl-ril.so" /vendor/lib64/libimpl-ril.so 2>/dev/null
    chcon u:object_r:vendor_file:s0 /vendor/lib64/libimpl-ril.so 2>/dev/null
    setprop ctl.restart vendor.ril-daemon
fi

# Fallback bind-mount for audio_route.xml
MODULE_AR_MD5=$(md5sum "$MODDIR/vendor/etc/audio_route.xml" 2>/dev/null | awk '{print $1}')
CURRENT_AR_MD5=$(md5sum /vendor/etc/audio_route.xml 2>/dev/null | awk '{print $1}')
if [ -n "$MODULE_AR_MD5" ] && [ "$CURRENT_AR_MD5" != "$MODULE_AR_MD5" ]; then
    chcon u:object_r:vendor_configs_file:s0 "$MODDIR/vendor/etc/audio_route.xml" 2>/dev/null
    mount -o bind "$MODDIR/vendor/etc/audio_route.xml" /vendor/etc/audio_route.xml 2>/dev/null
    chcon u:object_r:vendor_configs_file:s0 /vendor/etc/audio_route.xml 2>/dev/null
fi

# Safety check: if vendor.ril-daemon is in crash loop or restarting, enforce context and kick it
RIL_SVC=$(getprop init.svc.vendor.ril-daemon)
if [ "$RIL_SVC" = "restarting" ]; then
    chcon u:object_r:vendor_file:s0 /vendor/lib64/libimpl-ril.so 2>/dev/null
    setprop ctl.restart vendor.ril-daemon
fi

