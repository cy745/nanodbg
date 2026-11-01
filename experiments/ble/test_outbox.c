#include "nano_ble_outbox.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>
static uint8_t last[23]; static int last_len, fail_publish;
static int publish(const uint8_t *data, int n) {
    if (fail_publish) return -1;
    assert(n>0 && n<=23); memcpy(last,data,n); last_len=n; return 0;
}
static void exercise(int n) {
    nano_ble_outbox o; uint8_t data[216];
    for (int i=0;i<n;i++) data[i]=(uint8_t)i;
    nano_ble_outbox_init(&o,publish);
    assert(nano_ble_outbox_send(&o,7,data,n)==0);
    assert(nano_ble_outbox_send(&o,8,data,n)==-1);
    memset(data,0,sizeof data); /* published data must be copied */
    int total=(n+18)/19;
    for (int seq=0;seq<total;seq++) {
        int count=n-seq*19; if (count>19) count=19;
        assert(last_len==count+4 && last[0]==0xb0 && last[1]==7 && last[2]==seq && last[3]==total);
        for (int i=0;i<count;i++) assert(last[4+i]==(uint8_t)(seq*19+i));
        uint8_t wrong[3]={0xb1,8,seq};
        assert(nano_ble_outbox_ack(&o,wrong,3)==0 && o.seq==seq && o.pending);
        uint8_t ack[3]={0xb1,7,seq};
        fail_publish=1; assert(nano_ble_outbox_ack(&o,ack,3)==-1 && o.seq==seq && o.pending); fail_publish=0;
        assert(nano_ble_outbox_ack(&o,ack,3)==(seq+1==total));
    }
    assert(!o.pending && last_len==3 && last[0]==0xb2 && last[1]==7 && last[2]==total);
}
int main(void) {
    nano_ble_outbox o; uint8_t data[217]={0};
    nano_ble_outbox_init(&o,publish);
    assert(nano_ble_outbox_send(&o,1,data,0)==-1);
    assert(nano_ble_outbox_send(&o,1,data,217)==-1);
    assert(nano_ble_outbox_send(&o,1,0,1)==-1);
    fail_publish=1; assert(nano_ble_outbox_send(&o,1,data,1)==-1 && !o.pending); fail_publish=0;
    exercise(1); exercise(19); exercise(20); exercise(216);
    puts("outbox boundary and failure tests passed");
    return 0;
}
