#include "nano_ble_queue.h"
#include <assert.h>
int main(void) {
    nano_ble_queue q; uint8_t data[216]={1}; nano_ble_queue_init(&q);
    assert(!nano_ble_queue_front(&q)); assert(nano_ble_queue_pop(&q)==-1);
    assert(nano_ble_queue_push(&q,0,data,0)==-1);
    assert(nano_ble_queue_push(&q,0,data,217)==-1);
    for (int i=0;i<4;i++) { data[0]=i; assert(!nano_ble_queue_push(&q,i,data,216)); }
    data[0]=99; assert(nano_ble_queue_push(&q,9,data,1)==-1);
    for (int i=0;i<2;i++) { const nano_ble_queued_message *m=nano_ble_queue_front(&q); assert(m->id==i && m->data[0]==i && m->length==216); assert(!nano_ble_queue_pop(&q)); }
    for (int i=4;i<6;i++) { data[0]=i; assert(!nano_ble_queue_push(&q,i,data,1)); }
    for (int i=2;i<6;i++) { const nano_ble_queued_message *m=nano_ble_queue_front(&q); assert(m->id==i && m->data[0]==i); assert(!nano_ble_queue_pop(&q)); }
    assert(!nano_ble_queue_front(&q)); return 0;
}
