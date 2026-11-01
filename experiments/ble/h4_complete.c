#include "h4_complete.h"

void h4_complete_init(h4_complete_parser *p, uint16_t opcode) {
    p->opcode=opcode; p->type=0; p->header_used=0; p->header_size=0;
    p->remaining=0; p->event_used=0; p->result_length=0; p->status=0xff;
    p->response_event=0; p->accept_status=0; p->found=0;
}

static void finish(h4_complete_parser *p) {
    /* event = [number of command packets, opcode lo, opcode hi, status, ...] */
    if (!p->found && p->type==4 && p->header[0]==0x0e && p->event_used>=4 &&
        (unsigned)(p->event[1] | (p->event[2]<<8))==p->opcode) {
        p->status=p->event[3]; p->result_length=p->event_used-4;
        p->response_event=0x0e;
        p->found=1;
    } else if (!p->found && p->accept_status && p->type==4 &&
               p->header[0]==0x0f && p->event_used==4 &&
               (unsigned)(p->event[2] | (p->event[3]<<8))==p->opcode) {
        p->status=p->event[0]; p->result_length=0; p->response_event=0x0f;
        p->found=1;
    }
    p->type=0;
}

void h4_complete_feed(h4_complete_parser *p, const uint8_t *data, unsigned length) {
    for (unsigned i=0; i<length; i++) {
        uint8_t b=data[i];
        if (!p->type) {
            if (b==4) p->header_size=2;
            else if (b==2 || b==5) p->header_size=4;
            else if (b==3) p->header_size=3;
            else continue;
            p->type=b; p->header_used=0; p->event_used=0;
        } else if (p->header_used<p->header_size) {
            p->header[p->header_used++]=b;
            if (p->header_used==p->header_size) {
                if (p->type==4) p->remaining=p->header[1];
                else if (p->type==3) p->remaining=p->header[2];
                else {
                    p->remaining=p->header[2] | ((unsigned)p->header[3]<<8);
                    if (p->type==5) p->remaining &= 0x3fff;
                }
                if (!p->remaining) finish(p);
            }
        } else {
            if (p->type==4 && !p->found) p->event[p->event_used++]=b;
            if (!--p->remaining) finish(p);
        }
    }
}
