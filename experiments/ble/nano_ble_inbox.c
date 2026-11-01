#include "nano_ble_inbox.h"

void nano_ble_inbox_reset(nano_ble_inbox *inbox) {
    inbox->length=0; inbox->next=0; inbox->total=0;
    inbox->session[0]=inbox->session[1]=0;
}
int nano_ble_inbox_begin(nano_ble_inbox *inbox, const uint8_t session[2], int total) {
    if (!inbox || !session || total<1 || total>12) return NANO_INBOX_INVALID;
    inbox->session[0]=session[0]; inbox->session[1]=session[1];
    inbox->length=0; inbox->next=0; inbox->total=total;
    return 0;
}
int nano_ble_inbox_accept(nano_ble_inbox *inbox, const uint8_t *frame, int length,
                          nano_ble_publish_fn publish) {
    if (!inbox || !frame || !publish || length<6 || length>23 || frame[0]!=0xa1 ||
        frame[4]<1 || frame[4]>12 || frame[3]>=frame[4]) return NANO_INBOX_INVALID;
    if (inbox->total!=frame[4] || inbox->session[0]!=frame[1] || inbox->session[1]!=frame[2])
        return NANO_INBOX_IGNORED;
    int seq=frame[3];
    if (seq<inbox->next) return NANO_INBOX_DUPLICATE;
    if (seq!=inbox->next) return NANO_INBOX_IGNORED;
    if (inbox->length+length-5>NANO_BLE_INBOX_MAX) return NANO_INBOX_INVALID;
    if (publish(frame,length)) return NANO_INBOX_PUBLISH;
    for (int i=5;i<length;i++) inbox->data[inbox->length++]=frame[i];
    inbox->next++;
    return inbox->next==inbox->total ? NANO_INBOX_COMPLETE : NANO_INBOX_ACCEPTED;
}
