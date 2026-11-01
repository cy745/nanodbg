#include "nano_ble_inbox.h"
#include <assert.h>

static int fail, publications;
static int publish(const uint8_t *frame, int n) {
    assert(frame && n>=6 && n<=23);
    if (fail) { fail=0; return -1; }
    publications++; return 0;
}
int main(void) {
    nano_ble_inbox box; uint8_t session[2]={0x12,0x34};
    uint8_t frame[23]={0xa1,0x12,0x34,0,12};
    nano_ble_inbox_reset(&box);
    assert(nano_ble_inbox_begin(&box,session,0)==NANO_INBOX_INVALID);
    assert(nano_ble_inbox_begin(&box,session,12)==0);
    frame[3]=1;
    assert(nano_ble_inbox_accept(&box,frame,23,publish)==NANO_INBOX_IGNORED);
    frame[3]=0; frame[1]=0x99;
    assert(nano_ble_inbox_accept(&box,frame,23,publish)==NANO_INBOX_IGNORED);
    frame[1]=0x12; fail=1;
    assert(nano_ble_inbox_accept(&box,frame,23,publish)==NANO_INBOX_PUBLISH);
    assert(box.length==0 && box.next==0);
    for (int seq=0;seq<12;seq++) {
        frame[3]=(uint8_t)seq;
        for (int j=0;j<18;j++) frame[5+j]=(uint8_t)(seq*18+j);
        assert(nano_ble_inbox_accept(&box,frame,23,publish)==
               (seq==11 ? NANO_INBOX_COMPLETE : NANO_INBOX_ACCEPTED));
        assert(nano_ble_inbox_accept(&box,frame,23,publish)==NANO_INBOX_DUPLICATE);
    }
    assert(box.length==216 && box.next==12 && publications==12);
    for (int i=0;i<216;i++) assert(box.data[i]==i);
    assert(nano_ble_inbox_accept(&box,frame,24,publish)==NANO_INBOX_INVALID);
    nano_ble_inbox_reset(&box);
    assert(box.length==0 && box.total==0);
    return 0;
}
