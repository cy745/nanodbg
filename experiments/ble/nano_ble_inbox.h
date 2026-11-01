#ifndef NANO_BLE_INBOX_H
#define NANO_BLE_INBOX_H
#include <stdint.h>
#include "nano_ble_outbox.h" /* nano_ble_publish_fn */

#define NANO_BLE_INBOX_MAX 216
typedef struct {
    uint8_t data[NANO_BLE_INBOX_MAX], session[2];
    int length, next, total;
} nano_ble_inbox;

enum { NANO_INBOX_IGNORED=0, NANO_INBOX_ACCEPTED=1,
       NANO_INBOX_COMPLETE=2, NANO_INBOX_DUPLICATE=3,
       NANO_INBOX_INVALID=-1, NANO_INBOX_PUBLISH=-2 };
void nano_ble_inbox_reset(nano_ble_inbox *inbox);
/* Starts a session; caller controls arbitration and prevents session reuse. */
int nano_ble_inbox_begin(nano_ble_inbox *inbox, const uint8_t session[2], int total);
/* Accepts one a1 fragment. State advances only after publish(frame) succeeds.
 * Completion exposes data/length to the serialized application context; its
 * buffer remains valid until reset or another begin. This is not authentication. */
int nano_ble_inbox_accept(nano_ble_inbox *inbox, const uint8_t *frame, int length,
                          nano_ble_publish_fn publish);
#endif
