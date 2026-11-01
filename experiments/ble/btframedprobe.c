#include "hb_sdk.h"
#include "lvgl/lvgl.h"
#include "bt_hci.h"
static uint8_t frame[260], payload[26], last[26];
static volatile int pending; static int last_len, updates;
static uint8_t message[216], session[2]; static int msg_len, next_seq, total, duplicates;
static lv_timer_t *poll_timer;
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
                if (bytes > 0 && bytes <= 23 && !pending) {
                    for (int i = 0; i < bytes; i++) payload[i] = frame[ad+8+i];
                    payload_len = bytes; pending = 1;
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
static void update(lv_timer_t *t) {
    (void)t;
    if (!pending) return;
    int len=payload_len;
    if (len < 6 || payload[0] != 0xa1 || payload[4] == 0 || payload[4] > 12 ||
        payload[3] >= payload[4] || len-5 > 18) { pending=0; return; }
    int seq=payload[3];
    if (next_seq == 0) { session[0]=payload[1]; session[1]=payload[2]; total=payload[4]; }
    if (payload[1]!=session[0] || payload[2]!=session[1] || payload[4]!=total) { pending=0; return; }
    if (seq < next_seq) { duplicates++; pending=0; return; }
    if (seq != next_seq || msg_len + len - 5 > (int)sizeof message) { pending=0; return; }
    uint8_t data[32]={0}; data[0]=len+4; data[1]=len+3; data[2]=0xff; data[3]=0xff; data[4]=0xff;
    for (int i=0;i<len;i++) data[5+i]=payload[i];
    if (!command(0x2008,data,32)) {
        for (int i=5;i<len;i++) message[msg_len++]=payload[i];
        next_seq++; updates++;
        append("accepted "); hexbyte(seq); append("\n");
    }
    pending=0;
}
static void finish(lv_timer_t *t) {
    (void)t;
    if (poll_timer) lv_timer_delete(poll_timer);
    *(volatile uint32_t *)rxslot=(uint32_t)original;
    static const uint8_t no_scan[2]={0,0}, no_adv[1]={0};
    command(0x200c,no_scan,2); command(0x200a,no_adv,1);
    append("matches "); hexbyte(found & 255); hexbyte((found >> 8) & 255);
    append("malformed "); hexbyte(malformed & 255); append("updates "); hexbyte(updates); append("duplicates "); hexbyte(duplicates & 255);
    append("complete "); hexbyte(next_seq==total && total>0); append("message "); for (int i=0;i<msg_len;i++) hexbyte(message[i]); append("\n"); save();
}
static void start(lv_timer_t *t) {
    (void)t;
    if (!bt_is_on()) { append("bluetooth off\n"); save(); return; }
    static const uint8_t ap[15]={0xa0,0,0xa0,0,3,0,0,0,0,0,0,0,0,7,0};
    static const uint8_t ad[32]={0};
    static const uint8_t yes_adv[1]={1}, no_adv[1]={0};
    static const uint8_t sp[7]={0,0x60,0,0x30,0,0,0}, yes_scan[2]={1,0}, no_scan[2]={0,0};
    if (command(0x2006,ap,15) || command(0x2008,ad,32) || command(0x200a,yes_adv,1)) { save(); return; }
    if (command(0x200b,sp,7) || command(0x200c,yes_scan,2)) { command(0x200a,no_adv,1); save(); return; }
    uint32_t obj=*(volatile uint32_t *)BT_TRANSPORT_SLOT; rxslot=obj+BT_SLOT_RX; original=(rx_feed_t)*(volatile uint32_t *)rxslot;
    if (!original) { append("no rx\n"); command(0x200c,no_scan,2); command(0x200a,no_adv,1); save(); return; }
    *(volatile uint32_t *)rxslot=(uint32_t)&on_rx | 1u;
    append("both enabled\n"); save();
    poll_timer=lv_timer_create(update,50,0);
    lv_timer_t *timer=lv_timer_create(finish,65000,0); lv_timer_set_repeat_count(timer,1);
}
HB_APP_ENTRY(payload_entry) {
    hb_trace_init(); hb_wake_lock(true); append("framed-v1\n");
    lv_obj_t *label=lv_label_create(lv_screen_active()); lv_label_set_text(label,"BLE framed test");
    lv_timer_t *timer=lv_timer_create(start,5000,0); lv_timer_set_repeat_count(timer,1);
}
