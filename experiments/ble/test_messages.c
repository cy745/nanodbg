#include "nano_ble_messages.h"
#include <assert.h>

static uint8_t published[23];
static int published_len, fail_once;
static int publish(const uint8_t *data, int length) {
    if (fail_once) { fail_once=0; return -1; }
    published_len=length;
    for (int i=0;i<length;i++) published[i]=data[i];
    return 0;
}
int main(void) {
    nano_ble_messages m; nano_ble_outbox out; uint8_t id, byte=42;
    nano_ble_messages_init(&m); nano_ble_outbox_init(&out,publish);
    assert(nano_ble_messages_submit(&m,0,1,0)==NANO_MSG_INVALID);
    assert(nano_ble_messages_submit(&m,&byte,0,0)==NANO_MSG_INVALID);
    for (int i=0;i<4;i++) {
        byte=(uint8_t)i;
        assert(nano_ble_messages_submit(&m,&byte,1,&id)==NANO_MSG_OK);
        assert(id==0x80+i);
    }
    assert(nano_ble_messages_submit(&m,&byte,1,0)==NANO_MSG_FULL);
    fail_once=1;
    assert(nano_ble_messages_pump(&m,&out)==NANO_MSG_PUBLISH);
    assert(m.queue.count==4 && !out.pending);
    assert(nano_ble_messages_pump(&m,&out)==1);
    assert(published_len==5 && published[1]==0x80 && published[4]==0);
    assert(nano_ble_messages_pump(&m,&out)==NANO_MSG_BUSY);
    for (int i=0;i<127;i++) {
        if (i>=4) {
            byte=(uint8_t)i;
            assert(nano_ble_messages_submit(&m,&byte,1,&id)==NANO_MSG_OK);
            assert(id==0x80+i);
        }
        if (i) assert(nano_ble_messages_pump(&m,&out)==1);
        assert(out.id==0x80+i);
        uint8_t ack[3]={0xb1,out.id,0};
        assert(nano_ble_outbox_ack(&out,ack,3)==1);
    }
    assert(nano_ble_messages_pump(&m,&out)==0);
    assert(nano_ble_messages_submit(&m,&byte,1,0)==NANO_MSG_EXHAUSTED);
    return 0;
}
