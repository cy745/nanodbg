#ifndef NANO_H4_COMPLETE_H
#define NANO_H4_COMPLETE_H
#include <stdint.h>

/* One serialized H4 byte stream. Read result fields only after found != 0. */
typedef struct {
    uint16_t opcode;
    uint8_t type, header[4], event[255], status, response_event, accept_status;
    unsigned header_used, header_size, remaining, event_used, result_length;
    volatile int found;
} h4_complete_parser;

void h4_complete_init(h4_complete_parser *parser, uint16_t opcode);
void h4_complete_feed(h4_complete_parser *parser, const uint8_t *data, unsigned length);
#endif
