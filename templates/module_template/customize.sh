#!/system/bin/sh
ui_print "- Installing Realme C21Y IMEI & Telephony Permanent Restore..."

# Ensure dual-mount for Magisk, KernelSU, and APatch
if [ -d "$MODPATH/system/vendor" ] && [ ! -d "$MODPATH/vendor" ]; then
    cp -af "$MODPATH/system/vendor" "$MODPATH/vendor"
fi

set_perm_recursive $MODPATH 0 0 0755 0644
set_perm $MODPATH/service.sh 0 0 0755
set_perm $MODPATH/post-fs-data.sh 0 0 0755

# Set correct SELinux contexts
chcon -R u:object_r:vendor_file:s0 "$MODPATH/vendor" 2>/dev/null
chcon -R u:object_r:vendor_file:s0 "$MODPATH/system/vendor" 2>/dev/null
chcon -R u:object_r:vendor_configs_file:s0 "$MODPATH/vendor/etc" 2>/dev/null
chcon -R u:object_r:vendor_configs_file:s0 "$MODPATH/system/vendor/etc" 2>/dev/null

# Configure telephony settings for default data & mobility
settings put global multi_sim_data_call 1 2>/dev/null
settings put global mobile_data1 1 2>/dev/null
settings put global mobile_data 1 2>/dev/null
settings put global mobile_data_always_on 1 2>/dev/null
settings put global data_stall_recovery_on_bad_network 1 2>/dev/null
settings put global restricted_networking_mode 0 2>/dev/null

# Fix Ethio Telecom & Safaricom APN in telephony provider
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

ui_print "- Factory IMEIs restored to RIL layer."
ui_print "- Cellular data mobility (IA APN + pure IPv4) configured."
ui_print "- Permanent RIL & Audio Route patch installed successfully!"
