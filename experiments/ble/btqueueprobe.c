#include "hb_sdk.h"
#include "lvgl/lvgl.h"
#include "bt_hci.h"
#include "nano_ble_outbox.h"
#include "nano_ble_queue.h"
static uint8_t frame[260], payload[26], last[26];
static volatile int pending; static int last_len, updates;
static uint8_t message[217], incoming[216], session[2];
static int msg_len, next_seq, total, duplicates, complete, rx_len, rx_seq, rx_total, state, rounds;
static lv_timer_t *poll_timer, *deadline_timer, *notice_timer; static int stopping, reset_seen, late_reset_duplicates; static uint8_t reset_tag[2];
static nano_ble_outbox outbox; static int notice_acks, notice_sent_round;
static void finish(lv_timer_t *t);
static volatile int frame_len, frame_total, skip, found, payload_len, malformed;
static int round_no;
static int service_ready, tap_count, tap_dropped;
static nano_ble_queue tap_queue;
static uint32_t rxslot;
static rx_feed_t original;
static char report[4096]; static int rp;
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
    append("op "); hexbyte(op & 255); hexbyte(op >> 8); append("rc "); hexbyte(rc & 255); append("status "); hexbyte(status); append("\n"); return rc ? rc : (status ? -1 : 0);
}
static void save(void) { hb_fs_write("/Apps/Data/rawprobe.txt",report,rp+1); }
static int publish(const uint8_t *p, int len) {
#ifdef QUEUE_TEST_FAIL_ONCE
    static int injected_failure;
    if (!injected_failure && len>=4 && p[0]==0xb0 && p[1]==0x80) {
        injected_failure=1; append("injected publish failure\n"); return -1;
    }
#endif
    uint8_t data[32]={0}; data[0]=len+4; data[1]=len+3; data[2]=0xff; data[3]=0xff; data[4]=0xff;
    for (int i=0;i<len;i++) data[5+i]=p[i];
    if (command(0x2008,data,32)) return -1;
    updates++; return 0;
}
static void notice(lv_timer_t *t) {
    (void)t; notice_timer=0;
    if (stopping || (state!=0 && state!=3)) return;
    uint8_t startup[5]; const uint8_t *data=incoming; int n=rx_len;
    if (rounds==0) {
        uint32_t tick=lv_tick_get();
        for (int i=0;i<4;i++) startup[i]=(tick>>(i*8))&255;
        startup[4]=0; data=startup; n=5;
    }
    if (!nano_ble_outbox_send(&outbox,rounds & 255,data,n)) { append("outbox created length "); hexbyte(n); append("\n"); }

}
static void schedule_pump(void);
static void pump(lv_timer_t *t) {
    (void)t; notice_timer=0;
    if (!service_ready || stopping || outbox.pending ||
        (state!=0 && state!=3) || (state==3 && rounds>notice_sent_round)) return;
    const nano_ble_queued_message *m=nano_ble_queue_front(&tap_queue);
    if (m && !nano_ble_outbox_send(&outbox,m->id,m->data,m->length)) {
        append("queue sent id "); hexbyte(m->id); append("\n"); nano_ble_queue_pop(&tap_queue);
    } else if (m) { append("queue send failed; retry scheduled\n"); schedule_pump(); }
}
static void schedule_pump(void) {
    if (tap_queue.count && !notice_timer && !stopping) {
        notice_timer=lv_timer_create(pump,2000,0); lv_timer_set_repeat_count(notice_timer,1);
    }
}
static void tap_event(lv_event_t *event) {
    int button=(int)(uintptr_t)lv_event_get_user_data(event);
    if (!service_ready || stopping || tap_count>=127) { append("tap unavailable\n"); return; }
    uint8_t data[6]; uint32_t tick=lv_tick_get();
    for (int i=0;i<4;i++) data[i]=(tick>>(8*i))&255;
    data[4]=button; data[5]=tap_count+1;
    if (!nano_ble_queue_push(&tap_queue,0x80+tap_count,data,sizeof data)) {
        tap_count++; append("tap queued button "); hexbyte(button); append("count "); hexbyte(tap_count);
        append("depth "); hexbyte(tap_queue.count); append("\n");
        if (!outbox.pending && !notice_timer) pump(0);
    } else { tap_dropped++; append("tap queue full\n"); }
}
static int send_frame(int seq) {
    uint8_t data[23]={0xa2,session[0],session[1],seq,total};
    int off=seq*18, count=msg_len-off; if (count>18) count=18;
    for (int i=0;i<count;i++) data[5+i]=message[off+i];
    if (publish(data,count+5)) return -1;
    append("sent "); hexbyte(seq); append("\n"); return 0;
}
static void update(lv_timer_t *t) {
    (void)t;
    if (!pending) return;
    int len=payload_len;
    if (len==3 && payload[0]==0xb1 && outbox.pending) {
        int rc=nano_ble_outbox_ack(&outbox,payload,len);
        if (rc==1) { notice_acks++; append("outbox acknowledged "); hexbyte(rounds); append("\n"); schedule_pump(); }
        pending=0; return;
    }
    if (outbox.pending) { pending=0; return; }
    if (len==3 && payload[0]==0xb4 && !stopping && state==0 && !tap_queue.count && !notice_timer) {
        uint8_t ack[3]={0xb5,payload[1],payload[2]};
        if (!publish(ack,3)) {
            stopping=1; append("tap shutdown requested\n");
            lv_timer_t *shutdown=lv_timer_create(finish,2000,0); lv_timer_set_repeat_count(shutdown,1);
        }
        pending=0; return;
    }
    if (len==3 && payload[0]==0xb3 && state==3 && !stopping &&
        payload[1]==session[0] && payload[2]==session[1] && rounds>notice_sent_round) {
        notice(0); if (outbox.pending) { notice_sent_round=rounds; append("notice ready accepted\n"); }
        pending=0; return;
    }
    if (len==3 && payload[0]==0xa6 && payload[1]==session[0] && payload[2]==session[1] && state==3 && !stopping && !tap_queue.count && !notice_timer) {
        uint8_t ack[3]={0xa7,session[0],session[1]};
        if (!publish(ack,3)) {
            stopping=1; append("shutdown requested\n");
            lv_timer_t *shutdown=lv_timer_create(finish,2000,0); lv_timer_set_repeat_count(shutdown,1);
        }
        pending=0; return;
    }
    if (stopping) { pending=0; return; }
    if (len==3 && payload[0]==0xa8) {
        if (!reset_seen || reset_tag[0]!=payload[1] || reset_tag[1]!=payload[2]) {
            uint8_t ack[3]={0xa9,payload[1],payload[2]};
            if (!publish(ack,3)) {
                reset_seen=1; reset_tag[0]=payload[1]; reset_tag[1]=payload[2];
                append("reset state "); hexbyte(state); append("received "); hexbyte(rx_seq); append("\n");
                state=0; rx_len=rx_seq=rx_total=next_seq=0;
            }
        } else if (state==1 && rx_seq>0) late_reset_duplicates++;
        pending=0; return;
    }
    if ((tap_queue.count || notice_timer) && (state==0 || state==3)) { pending=0; return; }
    if (len >= 6 && payload[0]==0xa1 && payload[4]>0 && payload[4]<=12 && payload[3]<payload[4] && len<=23) {
        int seq=payload[3];
        if ((state==0 || state==3) && seq==0 && (state==0 || payload[1]!=session[0] || payload[2]!=session[1])) {
            session[0]=payload[1]; session[1]=payload[2]; rx_total=payload[4]; rx_seq=rx_len=0; state=1;
        }
        if (state==1 && payload[1]==session[0] && payload[2]==session[1] && payload[4]==rx_total) {
            if (seq==rx_seq && rx_len+len-5 <= (int)sizeof incoming) {
                if (!publish(payload,len)) { for (int i=5;i<len;i++) incoming[rx_len++]=payload[i]; rx_seq++; }
            } else if (seq<rx_seq) duplicates++;
        }
    } else if (len==3 && payload[0]==0xa4 && payload[1]==session[0] && payload[2]==session[1] && state==1 && rx_seq==rx_total) {
        msg_len=rx_len; total=(msg_len+17)/18;
        for (int i=0;i<msg_len;i++) message[i]=incoming[msg_len-1-i];
        next_seq=0; if (!send_frame(0)) { state=2; append("request "); for (int i=0;i<rx_len;i++) hexbyte(incoming[i]); append("\n"); }
    } else if (len==4 && payload[0]==0xa3 && payload[1]==session[0] && payload[2]==session[1] && state==2) {
        int seq=payload[3];
        if (seq<next_seq) duplicates++;
        else if (seq==next_seq) {
            if (seq+1==total) {
                uint8_t done[3]={0xa5,session[0],session[1]};
                if (!publish(done,3)) { state=3; complete=1; rounds++; append("round complete\n"); }
            } else if (!send_frame(seq+1)) next_seq++;
        }
    }
    pending=0;
}
static void finish(lv_timer_t *t) {
    if (deadline_timer && t != deadline_timer) lv_timer_delete(deadline_timer);
    if (poll_timer) lv_timer_delete(poll_timer);
    if (notice_timer) { lv_timer_delete(notice_timer); notice_timer=0; }
    service_ready=0;
    *(volatile uint32_t *)rxslot=(uint32_t)original;
    append("hook restored\n");
    static const uint8_t no_scan[2]={0,0}, no_adv[1]={0};
    command(0x200c,no_scan,2); command(0x200a,no_adv,1);
    append("tap dropped "); hexbyte(tap_dropped); append("queue remaining "); hexbyte(tap_queue.count); append("\n");
    append("matches "); hexbyte(found & 255); hexbyte((found >> 8) & 255);
    append("malformed "); hexbyte(malformed & 255); append("updates "); hexbyte(updates); append("duplicates "); hexbyte(duplicates & 255);
    append("notice acks "); hexbyte(notice_acks); append("late reset duplicates "); hexbyte(late_reset_duplicates & 255); append("complete "); hexbyte(complete); append("rounds "); hexbyte(rounds); append("length "); hexbyte(msg_len); append("\n"); save();
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
    append("both enabled\n");
    nano_ble_outbox_init(&outbox,publish);
    nano_ble_queue_init(&tap_queue);
    service_ready=1;
    notice(0);
    save();
    poll_timer=lv_timer_create(update,50,0);
    deadline_timer=lv_timer_create(finish,180000,0); lv_timer_set_repeat_count(deadline_timer,1);
}
HB_APP_ENTRY(payload_entry) {
    hb_trace_init(); hb_wake_lock(true); append("queued-tap-outbox-v1\n");
    lv_obj_t *label=lv_label_create(lv_screen_active()); lv_label_set_text(label,"BLE queued tap outbox");
    for (int i=0;i<2;i++) {
        lv_obj_t *button=lv_button_create(lv_screen_active());
        lv_obj_set_pos(button,20+i*115,80); lv_obj_set_size(button,85,70);
        lv_obj_add_event_cb(button,tap_event,LV_EVENT_CLICKED,(void *)(uintptr_t)(i+1));
        lv_obj_t *text=lv_label_create(button);
        lv_label_set_text(text,i ? "B" : "A"); lv_obj_center(text);
    }
    lv_timer_t *timer=lv_timer_create(start,5000,0); lv_timer_set_repeat_count(timer,1);
}
