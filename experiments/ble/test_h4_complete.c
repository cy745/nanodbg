#include "h4_complete.h"
#include <assert.h>

int main(void) {
    h4_complete_parser p;
    /* An unrelated LE event contains a complete-looking byte sequence. */
    const uint8_t noise[]={4,0x3e,9,4,0x0e,4,1,8,0x20,0,7,8};
    const uint8_t wrong[]={4,0x0e,4,1,9,0x20,0};
    const uint8_t short_cc[]={4,0x0e,3,1,8,0x20};
    const uint8_t correct[]={4,0x0e,6,1,8,0x20,0,0xaa,0xbb};
    h4_complete_init(&p,0x2008);
    h4_complete_feed(&p,noise,sizeof noise);
    h4_complete_feed(&p,wrong,sizeof wrong);
    h4_complete_feed(&p,short_cc,sizeof short_cc);
    assert(!p.found);
    for (unsigned i=0;i<sizeof correct;i++) h4_complete_feed(&p,correct+i,1);
    assert(p.found && p.response_event==0x0e && p.status==0 && p.result_length==2);
    assert(p.event[4]==0xaa && p.event[5]==0xbb);
    h4_complete_feed(&p,wrong,sizeof wrong);
    assert(p.status==0 && p.result_length==2 && p.event[4]==0xaa);

    /* Skip a large ACL frame rather than misreading bytes inside its payload. */
    const uint8_t acl[]={2,1,0,0x08,0x02};
    h4_complete_init(&p,0x2008);
    h4_complete_feed(&p,acl,sizeof acl);
    for (int i=0;i<65;i++) h4_complete_feed(&p,noise,8);
    assert(!p.found);
    const uint8_t failure[]={4,0x0e,4,1,8,0x20,0x0c};
    h4_complete_feed(&p,failure,sizeof failure);
    assert(p.found && p.status==0x0c && p.result_length==0);

    /* Only the opt-in parser accepts Command Status, and it must match. */
    const uint8_t wrong_status[]={4,0x0f,4,0x12,1,2,4};
    const uint8_t short_status[]={4,0x0f,3,0,1,1};
    const uint8_t status[]={4,0x0f,4,0x12,1,1,4};
    h4_complete_init(&p,0x0401);
    h4_complete_feed(&p,status,sizeof status);
    assert(!p.found);
    p.accept_status=1;
    h4_complete_feed(&p,wrong_status,sizeof wrong_status);
    h4_complete_feed(&p,short_status,sizeof short_status);
    assert(!p.found);
    for (unsigned i=0;i<sizeof status;i++) h4_complete_feed(&p,status+i,1);
    assert(p.found && p.response_event==0x0f && p.status==0x12 && !p.result_length);
    const uint8_t accepted[]={4,0x0f,4,0,1,1,4};
    h4_complete_init(&p,0x0401); p.accept_status=1;
    h4_complete_feed(&p,accepted,sizeof accepted);
    assert(p.found && p.response_event==0x0f && p.status==0 && !p.result_length);
    return 0;
}
