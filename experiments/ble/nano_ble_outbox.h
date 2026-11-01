#ifndef NANO_BLE_OUTBOX_H
#define NANO_BLE_OUTBOX_H
#include <stdint.h>
#define NANO_BLE_OUTBOX_MAX 216
typedef int (*nano_ble_publish_fn)(const uint8_t *, int);
typedef struct {
    uint8_t data[NANO_BLE_OUTBOX_MAX], id, seq, total, pending;
    int length;
    nano_ble_publish_fn publish;
} nano_ble_outbox;
/* Caller serializes access and provides an available advertising transport. */
void nano_ble_outbox_init(nano_ble_outbox *, nano_ble_publish_fn);
/* Copies 1..216 bytes; returns -1 for invalid/busy or transport failure. */
int nano_ble_outbox_send(nano_ble_outbox *, uint8_t id, const uint8_t *, int);
/* Returns 1 when fully acknowledged, 0 for intermediate/ignored, -1 on publish failure. */
int nano_ble_outbox_ack(nano_ble_outbox *, const uint8_t *, int);
#endif
