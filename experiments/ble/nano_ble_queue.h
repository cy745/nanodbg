#ifndef NANO_BLE_QUEUE_H
#define NANO_BLE_QUEUE_H
#include <stdint.h>
#define NANO_BLE_QUEUE_CAPACITY 4
#define NANO_BLE_QUEUE_MAX_BYTES 216

typedef struct {
    uint8_t id, data[NANO_BLE_QUEUE_MAX_BYTES];
    int length;
} nano_ble_queued_message;
typedef struct {
    nano_ble_queued_message messages[NANO_BLE_QUEUE_CAPACITY];
    unsigned head, count;
} nano_ble_queue;
void nano_ble_queue_init(nano_ble_queue *q);
/* Copies data; returns -1 for invalid input or a full queue. */
int nano_ble_queue_push(nano_ble_queue *q, uint8_t id, const uint8_t *data, int length);
/* The returned pointer stays valid until the next pop or queue mutation. */
const nano_ble_queued_message *nano_ble_queue_front(const nano_ble_queue *q);
int nano_ble_queue_pop(nano_ble_queue *q);
#endif
