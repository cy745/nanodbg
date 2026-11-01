#include "nano_ble_outbox.h"
static int send_frame(nano_ble_outbox *o, int seq) {
    uint8_t p[23]={0xb0,o->id,seq,o->total};
    int off=seq*19, n=o->length-off; if (n>19) n=19;
    for (int i=0;i<n;i++) p[4+i]=o->data[off+i];
    return o->publish(p,4+n);
}
void nano_ble_outbox_init(nano_ble_outbox *o, nano_ble_publish_fn publish) {
    o->pending=0; o->length=0; o->seq=0; o->total=0; o->publish=publish;
}
int nano_ble_outbox_send(nano_ble_outbox *o, uint8_t id, const uint8_t *data, int n) {
    if (!o || !o->publish || !data || n<1 || n>NANO_BLE_OUTBOX_MAX || o->pending) return -1;
    for (int i=0;i<n;i++) o->data[i]=data[i];
    o->id=id; o->seq=0; o->length=n; o->total=(n+18)/19;
    if (send_frame(o,0)) return -1;
    o->pending=1; return 0;
}
int nano_ble_outbox_ack(nano_ble_outbox *o, const uint8_t *p, int n) {
    if (!o || !p || n!=3 || !o->pending || p[0]!=0xb1 || p[1]!=o->id || p[2]!=o->seq) return 0;
    if (o->seq+1==o->total) {
        uint8_t done[3]={0xb2,o->id,o->total};
        if (o->publish(done,3)) return -1;
        o->pending=0; return 1;
    }
    if (send_frame(o,o->seq+1)) return -1;
    o->seq++; return 0;
}
