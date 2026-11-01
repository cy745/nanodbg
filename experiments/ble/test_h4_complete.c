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
    assert(p.found && p.status==0 && p.result_length==2);
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
    return 0;
}
