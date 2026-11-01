#include "l2cap_sdp_probe.h"
#include <assert.h>
#include <string.h>
int main(void) {
    l2cap_sdp_probe p={0}; uint8_t out[20];
    const uint8_t pending[]={12,0,1,0,3,0x73,8,0,0x40,0,0xe1,0,1,0,0,0};
    const uint8_t success[]={12,0,1,0,3,0x73,8,0,0x40,0,0xe1,0,0,0,0,0};
    const uint8_t request[]={12,0,1,0,4,1,8,0,0xe1,0,0,0,1,2,0,4};
    const uint8_t response[]={10,0,1,0,5,0x74,6,0,0xe1,0,0,0,0,0};
    const uint8_t config[]={8,0,1,0,4,0x74,4,0,0x40,0,0,0};
    const uint8_t answer[]={10,0,1,0,5,1,6,0,0x40,0,0,0,0,0};
    const uint8_t query[]={13,0,0x40,0,2,0x12,0x34,0,8,0x35,3,0x19,0x10,0,0,5,0};
    const uint8_t wrong_cid[]={12,0,1,0,3,0x73,8,0,0x40,0,0xe2,0,0,0,0,0};
    const uint8_t more_options[]={12,0,1,0,4,1,8,0,0xe1,0,1,0,1,2,0,4};
    const uint8_t failed_config[]={10,0,1,0,5,0x74,6,0,0xe1,0,0,0,1,0};
    l2cap_sdp_input(&p,pending,sizeof pending); assert(!l2cap_sdp_next(&p,out));
    l2cap_sdp_input(&p,wrong_cid,sizeof wrong_cid); assert(!l2cap_sdp_next(&p,out));
    l2cap_sdp_input(&p,success,sizeof success-1); assert(!l2cap_sdp_next(&p,out));
    l2cap_sdp_input(&p,success,sizeof success);
    assert(l2cap_sdp_next(&p,out)==sizeof config && !memcmp(out,config,sizeof config));
    l2cap_sdp_input(&p,more_options,sizeof more_options); assert(!l2cap_sdp_next(&p,out));
    l2cap_sdp_input(&p,failed_config,sizeof failed_config); assert(!l2cap_sdp_next(&p,out));
    l2cap_sdp_input(&p,request,sizeof request);
    assert(l2cap_sdp_next(&p,out)==sizeof answer && !memcmp(out,answer,sizeof answer));
    assert(!l2cap_sdp_next(&p,out));
    l2cap_sdp_input(&p,response,sizeof response);
    assert(l2cap_sdp_next(&p,out)==sizeof query && !memcmp(out,query,sizeof query));
    assert(!l2cap_sdp_next(&p,out));
    return 0;
}
