#ifndef NANO_L2CAP_SDP_PROBE_H
#define NANO_L2CAP_SDP_PROBE_H
#include <stdint.h>

/* Deliberately bounded diagnostic: one CID, one request, unfragmented frames.
 * This is not a general L2CAP or SDP implementation. */
typedef struct {
    uint16_t peer_cid;
    uint8_t peer_config_id, peer_config_seen, peer_config_answered;
    uint8_t our_config_sent, our_config_ok, query_sent;
    uint8_t info_id, info_pending;
} l2cap_sdp_probe;

static uint16_t l2cap_u16(const uint8_t *p) { return p[0] | ((uint16_t)p[1] << 8); }
static void l2cap_sdp_input(l2cap_sdp_probe *s, const uint8_t *p, unsigned n) {
    if (n < 8 || l2cap_u16(p) != n-4 || l2cap_u16(p+2) != 1 ||
        l2cap_u16(p+6) != n-8) return;
    if (p[4]==0x0a && p[5] && n==10 && l2cap_u16(p+8)==2) {
        s->info_id=p[5]; s->info_pending=1;
    }
    if (p[4]==3 && p[5]==0x73 && n==16 && l2cap_u16(p+10)==0x00e1 &&
        l2cap_u16(p+12)==0 && l2cap_u16(p+8)>=0x0040) s->peer_cid=l2cap_u16(p+8);
    if (p[4]==4 && p[5] && n>=12 && l2cap_u16(p+8)==0x00e1 &&
        l2cap_u16(p+10)==0) {
        /* Accept only no options or a single valid MTU option. */
        if (n==12 || (n==16 && p[12]==1 && p[13]==2 && l2cap_u16(p+14)>=48)) {
            s->peer_config_seen=1; s->peer_config_id=p[5];
        }
    }
    if (p[4]==5 && p[5]==0x74 && n>=14 && l2cap_u16(p+8)==0x00e1 &&
        l2cap_u16(p+10)==0 && l2cap_u16(p+12)==0 && s->our_config_sent)
        s->our_config_ok=1;
}

/* Returns one complete ACL payload to send, or zero if no action is ready. */
static unsigned l2cap_sdp_next(l2cap_sdp_probe *s, uint8_t out[20]) {
    if (s->info_pending) {
        /* Extended features: this diagnostic implements only basic mode. */
        const uint8_t v[]={12,0,1,0,0x0b,0,8,0,2,0,0,0,0,0,0,0};
        for (unsigned i=0;i<sizeof v;i++) out[i]=v[i];
        out[5]=s->info_id; s->info_pending=0; return sizeof v;
    }
    if (!s->peer_cid) return 0;
    if (!s->our_config_sent) {
        const uint8_t v[]={8,0,1,0,4,0x74,4,0,0,0,0,0};
        for (unsigned i=0;i<sizeof v;i++) out[i]=v[i];
        out[8]=s->peer_cid & 255; out[9]=s->peer_cid >> 8;
        s->our_config_sent=1; return sizeof v;
    }
    if (s->peer_config_seen && !s->peer_config_answered) {
        const uint8_t v[]={10,0,1,0,5,0,6,0,0,0,0,0,0,0};
        for (unsigned i=0;i<sizeof v;i++) out[i]=v[i];
        out[5]=s->peer_config_id; out[8]=s->peer_cid & 255; out[9]=s->peer_cid >> 8;
        s->peer_config_answered=1; return sizeof v;
    }
    if (s->our_config_ok && s->peer_config_answered && !s->query_sent) {
#ifdef ACL_RFCOMM_PROBE
        /* RFCOMM SABM, DLCI 0, command with poll bit, zero information. */
        const uint8_t v[]={4,0,0,0,3,0x3f,1,0x1c};
#else
        /* SDP ServiceSearchRequest: UUID 0x1000, max 5 handles, no continuation. */
        const uint8_t v[]={13,0,0,0,2,0x12,0x34,0,8,0x35,3,0x19,0x10,0,0,5,0};
#endif
        for (unsigned i=0;i<sizeof v;i++) out[i]=v[i];
        out[2]=s->peer_cid & 255; out[3]=s->peer_cid >> 8;
        s->query_sent=1; return sizeof v;
    }
    return 0;
}
#endif
