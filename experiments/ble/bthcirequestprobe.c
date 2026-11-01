/* One request per launch; only for the instrumented research firmware. */
#include "hb_sdk.h"
#include "lvgl/lvgl.h"
#include "bt_hci.h"
#include "h4_event.h"
#ifdef ACL_SDP_PROBE
#include "l2cap_sdp_probe.h"
#endif

static char report[2048];
static int used;
static void append(const char *s) { while (*s && used<(int)sizeof report-1) report[used++]=*s++; report[used]=0; }
static void hexbyte(unsigned b) { const char *h="0123456789abcdef"; char s[4]={h[(b>>4)&15],h[b&15],' ',0}; append(s); }
static h4_event_parser inquiry_event;
static rx_feed_t original_rx;
static volatile uint32_t *rx_slot;
static uint8_t connection_address[6];
static int connection_accepted;
#if defined(ACL_ECHO_PROBE) || defined(ACL_L2CAP_PROBE)
typedef struct {
    uint8_t reserved0, index;
    uint16_t reserved1, remaining, offset;
    uint32_t reserved2;
    uint8_t type, reserved3;
    uint16_t size;
    const void *data;
    uint32_t reserved4;
} acl_segment_buffer;
typedef int (*acl_send_t)(int type, int handle, const void *data, unsigned len);
static int acl_started, acl_send_rc;
#ifdef ACL_SDP_PROBE
static l2cap_sdp_probe sdp;
static unsigned sdp_read, sdp_ticks, sdp_tx_count;
static struct { int rc; unsigned len; uint8_t data[20]; } sdp_tx[3];
static void finish_connection(lv_timer_t *timer);
static void sdp_poll(lv_timer_t *timer) {
    while (sdp_read<inquiry_event.acl_record_count) {
        h4_acl_record *r=&inquiry_event.acl_records[sdp_read++];
        if ((r->flags & 0x30)==0x20 && r->length==r->saved)
            l2cap_sdp_input(&sdp,r->data,r->saved);
    }
    uint8_t data[20]; unsigned n;
    while ((n=l2cap_sdp_next(&sdp,data))!=0 && sdp_tx_count<3) {
        acl_segment_buffer buffer={0}; buffer.remaining=buffer.size=n; buffer.data=data;
        unsigned i=sdp_tx_count++;
        sdp_tx[i].len=n;
        for (unsigned j=0;j<n;j++) sdp_tx[i].data[j]=data[j];
        sdp_tx[i].rc=((acl_send_t)(BT_HCI_SEND_STAGED | 1u))
            (2,inquiry_event.acl_handle | 0x2000,&buffer,n);
    }
    if (++sdp_ticks>=30) { lv_timer_delete(timer); finish_connection(0); }
}
#endif
#ifdef ACL_L2CAP_PROBE
#ifndef L2CAP_PROBE_PSM
#define L2CAP_PROBE_PSM 3
#endif
static const uint8_t acl_request[]={8,0,1,0,2,0x73,4,0,
    L2CAP_PROBE_PSM & 255,(L2CAP_PROBE_PSM >> 8) & 255,0xe1,0};
#else
static const uint8_t acl_request[]={12,0,1,0,8,0x73,8,0,'N','A','N','O','A','C','L','!'};
#endif
#endif
static int inquiry_hook(uint8_t *buf, uint16_t len) {
    if (buf) h4_event_feed(&inquiry_event,buf,len);
    return original_rx ? original_rx(buf,len) : 0;
}
static void save(void) { hb_fs_write("/Apps/Data/hci-result.txt",report,used+1); }
static void finish_connection(lv_timer_t *timer) {
    (void)timer;
#if defined(ACL_ECHO_PROBE) || defined(ACL_L2CAP_PROBE)
    if (!acl_started && connection_accepted && inquiry_event.found && inquiry_event.data[0]==0) {
        acl_started=1;
        uint16_t handle=(inquiry_event.data[1] | ((uint16_t)inquiry_event.data[2]<<8)) & 0x0fff;
        inquiry_event.acl_handle=handle;
        inquiry_event.acl_capture=1;
        acl_segment_buffer buffer={0};
        buffer.remaining=buffer.size=sizeof acl_request;
        buffer.data=acl_request;
        acl_send_rc=((acl_send_t)(BT_HCI_SEND_STAGED | 1u))(2,handle | 0x2000,&buffer,sizeof acl_request);
#ifdef ACL_SDP_PROBE
        lv_timer_t *wait=lv_timer_create(sdp_poll,100,0);
        if (wait) return;
#else
        lv_timer_t *wait=lv_timer_create(finish_connection,3000,0);
        if (wait) { lv_timer_set_repeat_count(wait,1); return; }
#endif
    }
#endif
    append("connection-complete ");
    if (inquiry_event.found) {
        for (unsigned i=0;i<11;i++) hexbyte(inquiry_event.data[i]);
    } else append("none ");
    append("hook ");
    int restored=*rx_slot==((uint32_t)&inquiry_hook | 1u);
    if (restored) { *rx_slot=(uint32_t)original_rx; append("restored\n"); }
    else append("changed\n");
#if defined(ACL_ECHO_PROBE) || defined(ACL_L2CAP_PROBE)
    if (acl_started) {
        append("acl-send ");
        for (unsigned i=0;i<4;i++) hexbyte(((uint32_t)acl_send_rc >> (8*i)) & 255);
        append("seen "); hexbyte(inquiry_event.acl_seen>255 ? 255 : inquiry_event.acl_seen);
        append("echo ");
        if (inquiry_event.acl_found) {
            for (unsigned i=0;i<inquiry_event.acl_length;i++) hexbyte(inquiry_event.acl_data[i]);
        } else append("none ");
        append("\n");
#ifdef ACL_L2CAP_PROBE
#ifdef ACL_SDP_PROBE
        for (unsigned i=0;i<sdp_tx_count;i++) {
            append("acl-tx ");
            for (unsigned j=0;j<4;j++) hexbyte(((uint32_t)sdp_tx[i].rc >> (8*j)) & 255);
            for (unsigned j=0;j<sdp_tx[i].len;j++) hexbyte(sdp_tx[i].data[j]);
            append("\n");
        }
#endif
        for (unsigned i=0;i<inquiry_event.acl_record_count;i++) {
            h4_acl_record *r=&inquiry_event.acl_records[i];
            append("acl-frame "); hexbyte(r->flags); hexbyte(r->length & 255); hexbyte(r->length >> 8);
            for (unsigned j=0;j<r->saved;j++) hexbyte(r->data[j]);
            append("\n");
        }
        append("acl-dropped "); hexbyte(inquiry_event.acl_dropped>255 ? 255 : inquiry_event.acl_dropped); append("\n");
#endif
    }
#endif
    if (restored && connection_accepted && (!inquiry_event.found || inquiry_event.data[0]==0)) {
        uint8_t out[16], status=0xff, event=0, params[6]; int outlen=0;
        uint16_t op;
        if (inquiry_event.found && inquiry_event.data[0]==0) {
            op=0x0406;
            params[0]=inquiry_event.data[1]; params[1]=inquiry_event.data[2]; params[2]=0x13;
        } else {
            op=0x0408;
            for (unsigned i=0;i<6;i++) params[i]=connection_address[i];
        }
        int rc=bt_hci_cmd_ack(op,params,op==0x0406 ? 3 : 6,out,sizeof out,&outlen,&status,&event);
        append("connection-cleanup "); hexbyte(op & 255); hexbyte(op >> 8);
        hexbyte(rc & 255); hexbyte(status); hexbyte(event); append("\n");
    }
    save();
}
static void finish_inquiry(lv_timer_t *timer) {
    (void)timer;
    append("inquiry-complete ");
    if (inquiry_event.found) hexbyte(inquiry_event.data[0]); else append("none ");
    append("hook ");
    if (*rx_slot==((uint32_t)&inquiry_hook | 1u)) {
        *rx_slot=(uint32_t)original_rx;
        append("restored\n");
    } else append("changed\n");
    for (unsigned i=0;i<inquiry_event.record_count;i++) {
        h4_inquiry_record *r=&inquiry_event.records[i];
        append("inquiry-result "); hexbyte(r->code); hexbyte(r->length);
        for (unsigned j=0;j<r->saved;j++) hexbyte(r->data[j]);
        append("\n");
    }
    append("inquiry-dropped ");
    hexbyte(inquiry_event.dropped > 255 ? 255 : inquiry_event.dropped);
    append("\n");
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
        if ((opcode==0x0401 || (opcode==0x0405 && request[10]==13)) && bt_is_on()) {
            uint32_t obj=*(volatile uint32_t *)BT_TRANSPORT_SLOT;
            rx_slot=(volatile uint32_t *)(obj+BT_SLOT_RX);
            original_rx=(rx_feed_t)*rx_slot;
            if (original_rx) {
                h4_event_init(&inquiry_event,opcode==0x0401 ? 0x01 : 0x03,opcode==0x0401 ? 1 : 11);
                if (opcode==0x0405) {
                    inquiry_event.match_address=1;
                    for (unsigned i=0;i<6;i++) inquiry_event.address[i]=connection_address[i]=request[11+i];
                }
                *rx_slot=(uint32_t)&inquiry_hook | 1u;
                capture=1;
            }
        }
        int rc=bt_hci_cmd_ack(opcode,request+11,request[10],out,sizeof out,&outlen,&status,&response_event);
        append("rc "); hexbyte(rc & 255); append("status "); hexbyte(status);
        append("event "); hexbyte(response_event);
        append("data "); for (int i=0;i<outlen;i++) hexbyte(out[i]); append("\n");
        if (capture) {
            connection_accepted=(rc==0 && status==0);
            lv_timer_t *wait=lv_timer_create(opcode==0x0401 ? finish_inquiry : finish_connection,
                                             opcode==0x0401 ? 3000 : 7000,0);
            if (wait) lv_timer_set_repeat_count(wait,1);
            else if (opcode==0x0401) finish_inquiry(0); else finish_connection(0);
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
