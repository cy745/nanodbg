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
    const uint8_t result[]={4,0x22,4,1,2,3,4};
    h4_event_feed(&p,result,sizeof result);
    assert(p.record_count==1 && p.records[0].code==0x22 && p.records[0].length==4);
    assert(p.records[0].saved==4 && p.records[0].data[3]==4);
    const uint8_t long_header[]={4,0x2f,40};
    h4_event_feed(&p,long_header,sizeof long_header);
    for (uint8_t i=0;i<40;i++) h4_event_feed(&p,&i,1);
    assert(p.record_count==2 && p.records[1].length==40 && p.records[1].saved==32);
    assert(p.records[1].data[31]==31);
    for (int i=0;i<6;i++) h4_event_feed(&p,result,sizeof result);
    assert(p.record_count==6 && p.dropped==2);
    h4_event_init(&p,3,11);
    p.match_address=1;
    for (unsigned i=0;i<6;i++) p.address[i]=(uint8_t)(i+1);
    const uint8_t connection[]={4,3,11,0,0x34,0x02,1,2,3,4,5,6,1,0};
    const uint8_t wrong[]={4,3,11,0,0x34,0x02,1,2,3,4,5,7,1,0};
    h4_event_feed(&p,wrong,sizeof wrong);
    assert(!p.found);
    h4_event_feed(&p,connection,sizeof connection);
    assert(p.found && p.data[1]==0x34 && p.data[8]==6);
    p.acl_capture=1; p.acl_handle=0x234;
    const uint8_t wrong_length[]={2,0x34,0x22,8,0,5,0,1,0,9,0x73,0,0};
    h4_event_feed(&p,wrong_length,sizeof wrong_length);
    assert(p.acl_seen==1 && !p.acl_found);
    const uint8_t echo[]={2,0x34,0x22,8,0,4,0,1,0,9,0x73,0,0};
    for (unsigned i=0;i<sizeof echo;i++) h4_event_feed(&p,echo+i,1);
    assert(p.acl_seen==2 && p.acl_found && p.acl_length==8 && p.acl_data[5]==0x73);
    assert(p.acl_record_count==2 && p.acl_records[1].flags==0x20 &&
           p.acl_records[1].length==8 && p.acl_records[1].data[5]==0x73);
    const uint8_t big_header[]={2,0x34,0x22,65,0};
    h4_event_feed(&p,big_header,sizeof big_header);
    for (uint8_t i=0;i<65;i++) h4_event_feed(&p,&i,1);
    assert(p.acl_records[2].length==65 && p.acl_records[2].saved==64 &&
           p.acl_records[2].data[63]==63);
    for (int i=0;i<5;i++) h4_event_feed(&p,echo,sizeof echo);
    assert(p.acl_record_count==6 && p.acl_dropped==2);
    h4_event_init(&p,3,11); p.security_capture=1; p.security_handle=0x234;
    for (unsigned i=0;i<6;i++) p.security_address[i]=(uint8_t)(i+1);
    const uint8_t key_request[]={4,0x17,6,1,2,3,4,5,6};
    const uint8_t wrong_key_request[]={4,0x17,6,1,2,3,4,5,7};
    const uint8_t auth_complete[]={4,6,3,5,0x34,2};
    h4_event_feed(&p,wrong_key_request,sizeof wrong_key_request);
    for (unsigned i=0;i<sizeof key_request;i++) h4_event_feed(&p,key_request+i,1);
    h4_event_feed(&p,auth_complete,sizeof auth_complete);
    assert(p.security_count==2 && p.security_records[0].code==0x17 &&
           p.security_records[0].status==0xff && p.security_records[1].code==6 &&
           p.security_records[1].status==5);
    return 0;
}
