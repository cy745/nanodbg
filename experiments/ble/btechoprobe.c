#include "hb_sdk.h"
#include "lvgl/lvgl.h"
#include "bt_hci.h"
static uint8_t frame[260], payload[26];
static volatile int frame_len, frame_total, skip, found, payload_len, malformed;
static int round_no;
static uint32_t rxslot;
static rx_feed_t original;
static char report[1024]; static int rp;
static void append(const char *s) { while (*s && rp < (int)sizeof report - 1) report[rp++] = *s++; report[rp] = 0; }
static void hexbyte(unsigned v) { const char *h = "0123456789abcdef"; char s[4] = {h[(v >> 4) & 15], h[v & 15], ' ', 0}; append(s); }
static void parse_event(void) {
    if (frame_total < 5 || frame[1] != 0x3e || frame[3] != 2) return;
    int pos = 5, count = frame[4];
    while (count-- > 0) {
        if (pos + 10 > frame_total) { malformed++; return; }
        int n = frame[pos+8]; int end = pos + 9 + n;
        if (end >= frame_total) { malformed++; return; }
        int ad = pos+9;
        while (ad < end) {
            int len = frame[ad]; if (!len) break;
            if (ad + 1 + len > end) { malformed++; break; }
            if (len >= 7 && frame[ad+1] == 0xff && frame[ad+2] == 0xff && frame[ad+3] == 0xff &&
                frame[ad+4] == 'N' && frame[ad+5] == 'D' && frame[ad+6] == 'B' && frame[ad+7] == 'G') {
                int bytes = len - 7;
                if (bytes <= (int)sizeof payload && !found) {
                    for (int i = 0; i < bytes; i++) payload[i] = frame[ad+8+i];
                    payload_len = bytes;
                }
                found++;
            }
            ad += len + 1;
        }
        pos = end + 1;
    }
}
static void consume(uint8_t b) {
    if (skip) { skip--; return; }
    if (!frame_len) {
        if (b != 4 && b != 2 && b != 3) return;
        frame[0] = b; frame_len = 1; frame_total = 0; return;
    }
    frame[frame_len++] = b;
    if (frame[0] == 4 && frame_len == 3) frame_total = 3 + frame[2];
    else if (frame[0] == 2 && frame_len == 5) frame_total = 5 + frame[3] + (frame[4] << 8);
    else if (frame[0] == 3 && frame_len == 4) frame_total = 4 + frame[3];
    if (frame_total > (int)sizeof frame) { skip = frame_total - frame_len; frame_len = 0; return; }
    if (frame_total && frame_len == frame_total) { if (frame[0] == 4) parse_event(); frame_len = 0; }
}
static int on_rx(uint8_t *p, uint16_t n) { if (p) for (int i = 0; i < n; i++) consume(p[i]); return original ? original(p,n) : 0; }
static int command(uint16_t op, const void *p, uint8_t len) {
    uint8_t status=0xff; int n=0; int rc=bt_hci_cmd_status(op,p,len,0,0,&n,&status);
    append("op "); hexbyte(op & 255); hexbyte(op >> 8); append("rc "); hexbyte(rc & 255); append("status "); hexbyte(status); append("\n"); return rc;
}
static void save(void) { hb_fs_write("/Apps/Data/rawprobe.txt",report,rp+1); }
static void start_scan(lv_timer_t *t);
static void end_advertising(lv_timer_t *t) {
    (void)t;
    static const uint8_t disable[1]={0};
    if (command(0x200a,disable,1)) { append("advertise stop failed\n"); save(); return; }
    save();
    if (round_no < 2) {
        lv_timer_t *next=lv_timer_create(start_scan,100,0); lv_timer_set_repeat_count(next,1);
    }
}
static void finish_scan(lv_timer_t *t) {
    (void)t;
    *(volatile uint32_t *)rxslot=(uint32_t)original;
    static const uint8_t disable[2]={0,0};
    if (command(0x200c,disable,2)) { append("scan stop failed\n"); save(); return; }
    append("round "); hexbyte(round_no); append("matches "); hexbyte(found & 255); hexbyte((found >> 8) & 255);
    append("malformed "); hexbyte(malformed & 255); append("payload ");
    for (int i=0; i<payload_len; i++) hexbyte(payload[i]);
    append("\n");
    if (!found || !payload_len) {
        save();
        if (round_no < 2) { lv_timer_t *next=lv_timer_create(start_scan,100,0); lv_timer_set_repeat_count(next,1); }
        return;
    }
    static const uint8_t params[15]={0xa0,0,0xa0,0,3,0,0,0,0,0,0,0,0,7,0};
    if (command(0x2006,params,sizeof params)) { save(); return; }
    uint8_t data[32]={0};
    data[0]=payload_len+4; data[1]=payload_len+3; data[2]=0xff; data[3]=0xff; data[4]=0xff;
    for (int i=0; i<payload_len; i++) data[5+i]=payload[i];
    if (command(0x2008,data,sizeof data)) { save(); return; }
    static const uint8_t enable[1]={1};
    if (command(0x200a,enable,1)) { save(); return; }
    save();
    lv_timer_t *next=lv_timer_create(end_advertising,10000,0); lv_timer_set_repeat_count(next,1);
}
static void start_scan(lv_timer_t *t) {
    (void)t; round_no++;
    frame_len=frame_total=skip=found=payload_len=malformed=0;
    if (!bt_is_on()) { append("bluetooth off\n"); save(); return; }
    static const uint8_t params[7]={0,0x60,0,0x30,0,0,0};
    if (command(0x200b,params,7)) { save(); return; }
    static const uint8_t enable[2]={1,0};
    if (command(0x200c,enable,2)) { save(); return; }
    uint32_t obj=*(volatile uint32_t *)BT_TRANSPORT_SLOT; rxslot=obj+BT_SLOT_RX; original=(rx_feed_t)*(volatile uint32_t *)rxslot;
    if (!original) { append("no rx\n"); static const uint8_t disable[2]={0,0}; command(0x200c,disable,2); save(); return; }
    *(volatile uint32_t *)rxslot=(uint32_t)&on_rx | 1u;
    lv_timer_t *next=lv_timer_create(finish_scan,10000,0); lv_timer_set_repeat_count(next,1);
}
HB_APP_ENTRY(payload_entry) {
    hb_trace_init(); hb_wake_lock(true); append("echo-v1\n"); lv_obj_t *label=lv_label_create(lv_screen_active()); lv_label_set_text(label,"BLE round trip test");
    lv_timer_t *timer=lv_timer_create(start_scan,5000,0); lv_timer_set_repeat_count(timer,1);
}
