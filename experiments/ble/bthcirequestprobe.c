/* One request per launch; only for the instrumented research firmware. */
#include "hb_sdk.h"
#include "lvgl/lvgl.h"
#include "bt_hci.h"
#include "h4_event.h"

static char report[2048];
static int used;
static void append(const char *s) { while (*s && used<(int)sizeof report-1) report[used++]=*s++; report[used]=0; }
static void hexbyte(unsigned b) { const char *h="0123456789abcdef"; char s[4]={h[(b>>4)&15],h[b&15],' ',0}; append(s); }
static h4_event_parser inquiry_event;
static rx_feed_t original_rx;
static volatile uint32_t *rx_slot;
static int inquiry_hook(uint8_t *buf, uint16_t len) {
    if (buf) h4_event_feed(&inquiry_event,buf,len);
    return original_rx ? original_rx(buf,len) : 0;
}
static void save(void) { hb_fs_write("/Apps/Data/hci-result.txt",report,used+1); }
static void finish_inquiry(lv_timer_t *timer) {
    (void)timer;
    append("inquiry-complete ");
    if (inquiry_event.found) hexbyte(inquiry_event.data[0]); else append("none ");
    append("hook ");
    if (*rx_slot==((uint32_t)&inquiry_hook | 1u)) {
        *rx_slot=(uint32_t)original_rx;
        append("restored\n");
    } else append("changed\n");
    save();
}

static void run(lv_timer_t *timer) {
    (void)timer;
    uint8_t request[267], out[251], status=0xff, response_event=0;
    uint32_t n=hb_fs_read("/Apps/Data/hci-request.bin",request,sizeof request);
    if (!n) return; /* No request: leave any existing result untouched. */
    append("hci-request-v1\n");
    if (n<11 || n>266 || request[0]!='H' || request[1]!='C' || request[2]!='P' || request[3]!='1' || n!=11u+request[10]) {
        append("invalid request\n");
    } else {
        uint16_t opcode=request[8] | (request[9]<<8);
        int outlen=0;
        append("nonce "); for (int i=4;i<8;i++) hexbyte(request[i]);
        append("opcode "); hexbyte(request[8]); hexbyte(request[9]);
        append("params "); for (unsigned i=0;i<request[10];i++) hexbyte(request[11+i]); append("\n");
        int capture=0;
        if (opcode==0x0401 && bt_is_on()) {
            uint32_t obj=*(volatile uint32_t *)BT_TRANSPORT_SLOT;
            rx_slot=(volatile uint32_t *)(obj+BT_SLOT_RX);
            original_rx=(rx_feed_t)*rx_slot;
            if (original_rx) {
                h4_event_init(&inquiry_event,0x01,1);
                *rx_slot=(uint32_t)&inquiry_hook | 1u;
                capture=1;
            }
        }
        int rc=bt_hci_cmd_ack(opcode,request+11,request[10],out,sizeof out,&outlen,&status,&response_event);
        append("rc "); hexbyte(rc & 255); append("status "); hexbyte(status);
        append("event "); hexbyte(response_event);
        append("data "); for (int i=0;i<outlen;i++) hexbyte(out[i]); append("\n");
        if (capture) {
            lv_timer_t *wait=lv_timer_create(finish_inquiry,3000,0);
            if (wait) lv_timer_set_repeat_count(wait,1);
            else finish_inquiry(0);
            return;
        }
    }
    save();
}

HB_APP_ENTRY(payload_entry) {
    hb_trace_init(); hb_wake_lock(true);
    lv_obj_t *label=lv_label_create(lv_screen_active());
    lv_label_set_text(label,"HCI request probe");
    lv_timer_t *timer=lv_timer_create(run,5000,0);
    lv_timer_set_repeat_count(timer,1);
}
