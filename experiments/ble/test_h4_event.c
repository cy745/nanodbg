#include "h4_event.h"
#include <assert.h>
int main(void) {
    h4_event_parser p;
    const uint8_t noise[]={4,0x3e,4,4,1,1,0};
    const uint8_t short_event[]={4,1,0};
    const uint8_t event[]={4,1,1,0x12};
    h4_event_init(&p,1,1);
    h4_event_feed(&p,noise,sizeof noise);
    h4_event_feed(&p,short_event,sizeof short_event);
    assert(!p.found);
    for (unsigned i=0;i<sizeof event;i++) h4_event_feed(&p,event+i,1);
    assert(p.found && p.data[0]==0x12);
    const uint8_t other[]={4,1,1,0};
    h4_event_feed(&p,other,sizeof other);
    assert(p.data[0]==0x12);
    h4_event_init(&p,1,1);
    const uint8_t acl[]={2,1,0,4,0,4,1,1,0};
    h4_event_feed(&p,acl,sizeof acl);
    assert(!p.found);
    h4_event_feed(&p,other,sizeof other);
    assert(p.found && p.data[0]==0);
    return 0;
}
