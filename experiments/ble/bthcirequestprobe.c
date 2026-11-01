/* One request per launch; only for the instrumented research firmware. */
#include "hb_sdk.h"
#include "lvgl/lvgl.h"
#include "bt_hci.h"

static char report[2048];
static int used;
static void append(const char *s) { while (*s && used<(int)sizeof report-1) report[used++]=*s++; report[used]=0; }
static void hexbyte(unsigned b) { const char *h="0123456789abcdef"; char s[4]={h[(b>>4)&15],h[b&15],' ',0}; append(s); }

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
        int rc=bt_hci_cmd_ack(opcode,request+11,request[10],out,sizeof out,&outlen,&status,&response_event);
        append("rc "); hexbyte(rc & 255); append("status "); hexbyte(status);
        append("event "); hexbyte(response_event);
        append("data "); for (int i=0;i<outlen;i++) hexbyte(out[i]); append("\n");
    }
    hb_fs_write("/Apps/Data/hci-result.txt",report,used+1);
}

HB_APP_ENTRY(payload_entry) {
    hb_trace_init(); hb_wake_lock(true);
    lv_obj_t *label=lv_label_create(lv_screen_active());
    lv_label_set_text(label,"HCI request probe");
    lv_timer_t *timer=lv_timer_create(run,5000,0);
    lv_timer_set_repeat_count(timer,1);
}
