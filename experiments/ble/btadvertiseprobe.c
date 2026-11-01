#include "hb_sdk.h"
#include "lvgl/lvgl.h"
#include "bt_hci.h"
static char report[512]; static int rp;
static void append(const char *s) { while (*s && rp < (int)sizeof report - 1) report[rp++] = *s++; report[rp] = 0; }
static void hexbyte(unsigned v) { const char *h = "0123456789abcdef"; char s[4] = {h[(v >> 4) & 15], h[v & 15], ' ', 0}; append(s); }
static int command(uint16_t op, const void *p, uint8_t len) {
    uint8_t status = 0xff; int n = 0;
    int rc = bt_hci_cmd_status(op, p, len, 0, 0, &n, &status);
    append("op "); hexbyte(op & 255); hexbyte(op >> 8); append("rc "); hexbyte(rc & 255); append("status "); hexbyte(status); append("\n");
    return rc;
}
static void save(void) { hb_fs_write("/Apps/Data/rawprobe.txt", report, rp + 1); }
static void finish(lv_timer_t *t) { (void)t; static const uint8_t disable[1]={0}; command(0x200a,disable,1); save(); }
static void run(lv_timer_t *t) {
    (void)t; append("advertise-file-v1\n");
    if (!bt_is_on()) { append("bluetooth off\n"); save(); return; }
    static const uint8_t params[15] = {0xa0,0,0xa0,0,3,0,0,0,0,0,0,0,0,7,0};
    if (command(0x2006,params,sizeof params)) { save(); return; }
    uint8_t data[32] = {0}, payload[27];
    uint32_t n = hb_fs_read("/Apps/Data/ble-tx.bin", payload, sizeof payload);
    if (!n || n > 26) { append("invalid or missing payload\n"); save(); return; }
    for (uint32_t i = 0; i < n; i++) data[5+i] = payload[i];
    data[0] = n + 4; data[1] = n + 3; data[2] = 0xff; data[3] = 0xff; data[4] = 0xff;
    append("payload length "); hexbyte(n); append("\n");
    if (command(0x2008,data,sizeof data)) { save(); return; }
    static const uint8_t enable[1] = {1};
    if (command(0x200a,enable,1)) { save(); return; }
    lv_timer_t *finish_timer=lv_timer_create(finish,15000,0); lv_timer_set_repeat_count(finish_timer,1);
}
HB_APP_ENTRY(payload_entry) {
    hb_trace_init(); hb_wake_lock(true);
    lv_obj_t *label=lv_label_create(lv_screen_active()); lv_label_set_text(label,"BLE advertising test");
    lv_timer_t *timer=lv_timer_create(run,5000,0); lv_timer_set_repeat_count(timer,1);
}
