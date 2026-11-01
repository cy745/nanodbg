#ifndef NANO_H4_EVENT_H
#define NANO_H4_EVENT_H
#include <stdint.h>
#define H4_INQUIRY_MAX_RECORDS 6
#define H4_INQUIRY_MAX_BYTES 32
typedef struct {
    uint8_t code, length, saved, data[H4_INQUIRY_MAX_BYTES];
} h4_inquiry_record;
typedef struct { uint8_t flags, saved, data[64]; uint16_t length; } h4_acl_record;

/* Captures the first exact event code/length in a serialized H4 stream.
 * As with h4_complete, the stream must start at a packet boundary. */
typedef struct {
    uint8_t type, header[4], code, wanted_length, data[255];
    unsigned header_size, header_used, remaining, used;
    volatile int found;
    uint8_t match_address, address[6];
    volatile int acl_capture, acl_found;
    uint16_t acl_handle, acl_length;
    volatile unsigned acl_seen;
    uint8_t acl_scratch[64], acl_data[64];
    h4_acl_record acl_records[12];
    volatile unsigned acl_record_count, acl_dropped;
    volatile int security_capture;
    uint8_t security_address[6], security_scratch[7];
    uint16_t security_handle;
    struct { uint8_t code, status; } security_records[8];
    volatile unsigned security_count, security_dropped;
    uint8_t scratch[H4_INQUIRY_MAX_BYTES];
    h4_inquiry_record records[H4_INQUIRY_MAX_RECORDS];
    volatile unsigned record_count, dropped;
} h4_event_parser;

static void h4_event_init(h4_event_parser *p, uint8_t code, uint8_t length) {
    p->type=0; p->header_size=0; p->header_used=0; p->remaining=0; p->used=0;
    p->code=code; p->wanted_length=length; p->found=0;
    p->match_address=0;
    p->acl_capture=0; p->acl_found=0; p->acl_seen=0; p->acl_length=0;
    p->acl_record_count=0; p->acl_dropped=0;
    p->security_capture=0; p->security_count=0; p->security_dropped=0;
    p->record_count=0; p->dropped=0;
}

static int h4_is_inquiry_result(uint8_t code) {
    return code==0x02 || code==0x22 || code==0x2f;
}

static void h4_event_finish(h4_event_parser *p) {
    if (p->type==4 && p->security_capture) {
        unsigned code=p->header[0], length=p->header[1], match=0, status=0xff;
        if ((code==0x06 && length==3) || (code==0x05 && length==4)) {
            match=((p->security_scratch[1] | ((unsigned)p->security_scratch[2]<<8)) & 0x0fff)==p->security_handle;
            status=p->security_scratch[0];
        } else if ((code==0x16 && length==6) || (code==0x17 && length==6) ||
                   (code==0x18 && length==23) || (code==0x31 && length==6) ||
                   (code==0x32 && length==9) || (code==0x33 && length==10) ||
                   (code==0x34 && length==6) || (code==0x3b && length==10) ||
                   (code==0x36 && length==7)) {
            unsigned offset=code==0x36 ? 1 : 0;
            match=1;
            for (unsigned i=0;i<6;i++) if (p->security_scratch[i+offset]!=p->security_address[i]) match=0;
            if (code==0x36) status=p->security_scratch[0];
        }
        if (match) {
            if (p->security_count<8) {
                p->security_records[p->security_count].code=code;
                p->security_records[p->security_count].status=status;
                p->security_count++;
            } else p->security_dropped++;
        }
    }
    if (p->type==2 && p->acl_capture &&
        ((p->header[0] | ((unsigned)p->header[1]<<8)) & 0x0fff)==p->acl_handle) {
        unsigned length=p->header[2] | ((unsigned)p->header[3]<<8);
        p->acl_seen++;
        if (p->acl_record_count < 12) {
            h4_acl_record *r=&p->acl_records[p->acl_record_count];
            r->flags=p->header[1] & 0xf0; r->length=length;
            r->saved=length < 64 ? length : 64;
            for (unsigned j=0;j<r->saved;j++) r->data[j]=p->acl_scratch[j];
            p->acl_record_count++;
        } else p->acl_dropped++;
        if (!p->acl_found && (p->header[1] & 0x30)==0x20 && length>=8 && length<=64 &&
            (p->acl_scratch[0] | ((unsigned)p->acl_scratch[1]<<8))==length-4 &&
            (p->acl_scratch[6] | ((unsigned)p->acl_scratch[7]<<8))==length-8 &&
            p->acl_scratch[2]==1 && p->acl_scratch[3]==0 &&
            p->acl_scratch[4]==9 && p->acl_scratch[5]==0x73) {
            p->acl_length=length;
            for (unsigned j=0;j<length;j++) p->acl_data[j]=p->acl_scratch[j];
            p->acl_found=1;
        }
    }
    if (p->type==4 && h4_is_inquiry_result(p->header[0])) {
        if (p->record_count < H4_INQUIRY_MAX_RECORDS) {
            h4_inquiry_record *r=&p->records[p->record_count];
            r->code=p->header[0]; r->length=p->header[1];
            r->saved=r->length < H4_INQUIRY_MAX_BYTES ? r->length : H4_INQUIRY_MAX_BYTES;
            for (unsigned j=0;j<r->saved;j++) r->data[j]=p->scratch[j];
            p->record_count++;
        } else p->dropped++;
    }
    if (!p->found && p->type==4 && p->header[0]==p->code &&
        p->header[1]==p->wanted_length) {
        int match=1;
        if (p->match_address) {
            if (p->wanted_length<9) match=0;
            else for (unsigned j=0;j<6;j++)
                if (p->data[3+j]!=p->address[j]) match=0;
        }
        if (match) p->found=1;
    }
    p->type=0;
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
                    h4_event_finish(p);
                }
            }
        } else {
            if (p->type==4 && p->security_capture &&
                p->header[1]-p->remaining < (p->header[0]==0x36 ? 7u :
                    (p->header[0]==0x06 ? 3u : (p->header[0]==0x05 ? 4u : 6u))))
                p->security_scratch[p->header[1]-p->remaining]=b;
            if (p->type==2 && p->acl_capture &&
                ((p->header[2] | ((unsigned)p->header[3]<<8))-p->remaining)<64)
                p->acl_scratch[(p->header[2] | ((unsigned)p->header[3]<<8))-p->remaining]=b;
            if (p->type==4 && h4_is_inquiry_result(p->header[0]) &&
                p->header[1]-p->remaining < H4_INQUIRY_MAX_BYTES)
                p->scratch[p->header[1]-p->remaining]=b;
            if (!p->found && p->type==4 && p->header[0]==p->code &&
                p->header[1]==p->wanted_length) p->data[p->used++]=b;
            if (!--p->remaining) h4_event_finish(p);
        }
    }
}
#endif
