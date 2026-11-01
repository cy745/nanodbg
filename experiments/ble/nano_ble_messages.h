#ifndef NANO_BLE_MESSAGES_H
#define NANO_BLE_MESSAGES_H
#include "nano_ble_queue.h"
#include "nano_ble_outbox.h"

/* Experimental one-boot device outbox; all operations require one serialized
 * application context. The caller owns radio setup, scheduling and ACKs. */
typedef struct {
    nano_ble_queue queue;
    unsigned next_id;
} nano_ble_messages;

enum { NANO_MSG_OK=0, NANO_MSG_INVALID=-1, NANO_MSG_FULL=-2,
       NANO_MSG_EXHAUSTED=-3, NANO_MSG_BUSY=-4, NANO_MSG_PUBLISH=-5 };

void nano_ble_messages_init(nano_ble_messages *messages);
/* Copies 1..216 bytes and assigns an ID from 0x80..0xfe. A successful return
 * means queued, not delivered. IDs are never reused until reinitialization. */
int nano_ble_messages_submit(nano_ble_messages *messages, const uint8_t *data,
                             int length, uint8_t *assigned_id);
/* 1: published and dequeued, 0: no message, negative: see status above.
 * On publish failure the front message remains queued for the caller to retry. */
int nano_ble_messages_pump(nano_ble_messages *messages, nano_ble_outbox *outbox);
#endif
