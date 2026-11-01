/*
 * bt_hci.c — 同步 HCI 命令实现
 */
#include "bt_hci.h"

typedef int (*hci_send_t)(int type, int opcode, int len);
typedef int (*hci_send_staged_t)(int type, int opcode, const void *params, unsigned len);
typedef int (*rx_feed_t)(uint8_t *buf, uint16_t len);

/* Firmware scatter/gather reader consumes a 12-byte header followed by a
 * 12-byte segment. Keep this object alive through the synchronous send. */
typedef struct {
    uint8_t reserved0, index;
    uint16_t reserved1, remaining, offset;
    uint32_t reserved2;
    uint8_t type, reserved3;
    uint16_t size;
    const void *data;
    uint32_t reserved4;
} hci_segment_buffer;

static rx_feed_t    s_orig_rx;
static volatile uint32_t s_slot;
static volatile int s_armed;
static volatile int s_len;
static uint8_t      s_cap[512];

static int hook_rx(uint8_t *buf, uint16_t len)
{
    if (s_armed && buf) {
        int n = (int)len;
        for (int i = 0; i < n && s_len < (int)sizeof s_cap; i++)
            s_cap[s_len++] = buf[i];
    }
    return s_orig_rx ? s_orig_rx(buf, len) : 0;
}

static void busy_wait(volatile int loops)
{
    while (loops-- > 0) {
    }
}

bool bt_is_on(void)
{
    uint32_t obj = *(volatile uint32_t *)BT_TRANSPORT_SLOT;
    if (obj < 0x08000000u || obj >= 0x0A000000u)
        return false;
    return ((*(volatile uint32_t *)(obj + BT_SLOT_SEND) & ~1u) != BT_STUB_SEND);
}

/* 在截获缓冲里找 Command Complete（0x04 0x0E ... opcode 匹配）。
 * 返回 1 = 找到，*payload 和 *plen 指向参数区（status 之后）。 */
static int find_cc(uint16_t opcode, uint8_t **payload, int *plen, uint8_t *status)
{
    int n = s_len;
    for (int i = 0; i + 5 < n; i++) {
        if (s_cap[i] != 0x04 || s_cap[i + 1] != 0x0E)
            continue;
        int pl = s_cap[i + 2];
        if (i + 3 + pl > n)
            continue;
        int op = s_cap[i + 4] | (s_cap[i + 5] << 8);
        if (op != opcode)
            continue;
        /* 参数: [ncmd][op_lo][op_hi][status][data...] */
        uint8_t *p = &s_cap[i + 6];
        int remain = (i + 3 + pl) - (i + 6);
        if (remain < 1)
            return 0;
        if (status) *status = p[0];
        *payload = p + 1;          /* 跳过 status */
        *plen = remain - 1;
        return (p[0] == 0) ? 1 : -1;   /* 1=成功, -1=状态非0 */
    }
    return 0;
}

int bt_hci_cmd_status(uint16_t opcode, const void *params, uint8_t plen,
                      uint8_t *out, int outmax, int *outlen, uint8_t *status)
{
    if (status) *status = 0xff;
    if (outlen)
        *outlen = 0;
    if (plen && !params)
        return BT_ERR_ARGUMENT;
    if (!bt_is_on())
        return BT_ERR_OFF;

    uint32_t obj = *(volatile uint32_t *)BT_TRANSPORT_SLOT;
    if (obj < 0x08000000u || obj >= 0x0A000000u)
        return BT_ERR_NO_TRANSPORT;

    /* 1) 装钩子 */
    s_orig_rx = (rx_feed_t)(*(volatile uint32_t *)(obj + BT_SLOT_RX));
    if (!s_orig_rx)
        return BT_ERR_NO_TRANSPORT;
    s_len = 0;
    s_armed = 1;
    s_slot = obj + BT_SLOT_RX;
    *(volatile uint32_t *)s_slot = (uint32_t)&hook_rx | 1u;

    /* 0x83daa3c reads a segment descriptor, not a flat byte array.
     * Both its cursor and the staging pointer are mutable global state. */
    hci_segment_buffer buffer = {0};
    buffer.remaining = plen;
    buffer.size = plen;
    buffer.data = params;
    int rc = plen
        ? ((hci_send_staged_t)(BT_HCI_SEND_STAGED | 1u))(1, opcode, &buffer, plen)
        : ((hci_send_t)(BT_HCI_SEND_THUNK | 1u))(1, opcode, 0);
    (void)rc;

    /* 3) 轮询等待响应（约 300 ms 上限） */
    uint8_t *payload = 0;
    int plen_out = 0;
    int found = 0;
    for (int spin = 0; spin < 3000 && !found; spin++) {
        busy_wait(3000);
        found = find_cc(opcode, &payload, &plen_out, status);
    }

    /* 4) 恢复原指针 */
    s_armed = 0;
    *(volatile uint32_t *)s_slot = (uint32_t)s_orig_rx;

    if (found == 0)
        return BT_ERR_TIMEOUT;
    if (found < 0)
        return BT_ERR_STATUS;

    if (out && outmax > 0) {
        int n = plen_out < outmax ? plen_out : outmax;
        for (int i = 0; i < n; i++)
            out[i] = payload[i];
        if (outlen)
            *outlen = n;
    }
    return BT_OK;
}

int bt_hci_cmd(uint16_t opcode, const void *params, uint8_t plen,
               uint8_t *out, int outmax, int *outlen)
{
    return bt_hci_cmd_status(opcode, params, plen, out, outmax, outlen, 0);
}

int bt_read_bd_addr(uint8_t addr[6])
{
    uint8_t buf[8];
    int n = 0;
    int r = bt_hci_cmd(BT_OP_READ_BD_ADDR, 0, 0, buf, sizeof buf, &n);
    if (r == BT_OK && n >= 6) {
        for (int i = 0; i < 6; i++)
            addr[i] = buf[i];
    }
    return r;
}

int bt_read_local_name(char name[248])
{
    int n = 0;
    int r = bt_hci_cmd(BT_OP_READ_LOCAL_NAME, 0, 0, (uint8_t *)name, 247, &n);
    if (r == BT_OK) {
        name[n] = 0;
    }
    return r;
}
