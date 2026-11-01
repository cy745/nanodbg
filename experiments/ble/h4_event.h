#ifndef NANO_H4_EVENT_H
#define NANO_H4_EVENT_H
#include <stdint.h>

/* Captures the first exact event code/length in a serialized H4 stream.
 * As with h4_complete, the stream must start at a packet boundary. */
typedef struct {
    uint8_t type, header[4], code, wanted_length, data[255];
    unsigned header_size, header_used, remaining, used;
    volatile int found;
} h4_event_parser;

static void h4_event_init(h4_event_parser *p, uint8_t code, uint8_t length) {
    p->type=0; p->header_size=0; p->header_used=0; p->remaining=0; p->used=0;
    p->code=code; p->wanted_length=length; p->found=0;
}

static void h4_event_feed(h4_event_parser *p, const uint8_t *data, unsigned length) {
    for (unsigned i=0; i<length; i++) {
        uint8_t b=data[i];
        if (!p->type) {
            if (b==4) p->header_size=2;
            else if (b==2 || b==5) p->header_size=4;
            else if (b==3) p->header_size=3;
            else continue;
            p->type=b; p->header_used=0; p->used=0;
        } else if (p->header_used<p->header_size) {
            p->header[p->header_used++]=b;
            if (p->header_used==p->header_size) {
                if (p->type==4) p->remaining=p->header[1];
                else if (p->type==3) p->remaining=p->header[2];
                else {
                    p->remaining=p->header[2] | ((unsigned)p->header[3]<<8);
                    if (p->type==5) p->remaining &= 0x3fff;
                }
                if (!p->remaining) {
                    if (!p->found && p->type==4 && p->header[0]==p->code && !p->wanted_length)
                        p->found=1;
                    p->type=0;
                }
            }
        } else {
            if (!p->found && p->type==4 && p->header[0]==p->code &&
                p->header[1]==p->wanted_length) p->data[p->used++]=b;
            if (!--p->remaining) {
                if (!p->found && p->type==4 && p->header[0]==p->code &&
                    p->header[1]==p->wanted_length) p->found=1;
                p->type=0;
            }
        }
    }
}
#endif
