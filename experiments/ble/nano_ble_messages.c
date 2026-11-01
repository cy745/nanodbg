#include "nano_ble_messages.h"

void nano_ble_messages_init(nano_ble_messages *messages) {
    nano_ble_queue_init(&messages->queue);
    messages->next_id=0x80;
}

int nano_ble_messages_submit(nano_ble_messages *messages, const uint8_t *data,
                             int length, uint8_t *assigned_id) {
    if (!messages || !data || length<1 || length>NANO_BLE_QUEUE_MAX_BYTES)
        return NANO_MSG_INVALID;
    if (messages->next_id>0xfe) return NANO_MSG_EXHAUSTED;
    if (messages->queue.count>=NANO_BLE_QUEUE_CAPACITY) return NANO_MSG_FULL;
    uint8_t id=(uint8_t)messages->next_id;
    if (nano_ble_queue_push(&messages->queue,id,data,length)) return NANO_MSG_INVALID;
    messages->next_id++;
    if (assigned_id) *assigned_id=id;
    return NANO_MSG_OK;
}

int nano_ble_messages_pump(nano_ble_messages *messages, nano_ble_outbox *outbox) {
    if (!messages || !outbox) return NANO_MSG_INVALID;
    const nano_ble_queued_message *front=nano_ble_queue_front(&messages->queue);
    if (!front) return 0;
    if (outbox->pending) return NANO_MSG_BUSY;
    if (nano_ble_outbox_send(outbox,front->id,front->data,front->length)) return NANO_MSG_PUBLISH;
    nano_ble_queue_pop(&messages->queue);
    return 1;
}
