#include "nano_ble_queue.h"
void nano_ble_queue_init(nano_ble_queue *q) { q->head=0; q->count=0; }
int nano_ble_queue_push(nano_ble_queue *q, uint8_t id, const uint8_t *data, int length) {
    if (!q || !data || length<1 || length>NANO_BLE_QUEUE_MAX_BYTES || q->count>=NANO_BLE_QUEUE_CAPACITY) return -1;
    nano_ble_queued_message *m=&q->messages[(q->head+q->count)%NANO_BLE_QUEUE_CAPACITY];
    m->id=id; m->length=length;
    for (int i=0;i<length;i++) m->data[i]=data[i];
    q->count++; return 0;
}
const nano_ble_queued_message *nano_ble_queue_front(const nano_ble_queue *q) {
    return q && q->count ? &q->messages[q->head] : 0;
}
int nano_ble_queue_pop(nano_ble_queue *q) {
    if (!q || !q->count) return -1;
    q->head=(q->head+1)%NANO_BLE_QUEUE_CAPACITY; q->count--; return 0;
}
