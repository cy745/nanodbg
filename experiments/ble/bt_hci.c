/*
 * bt_hci.c — 同步 HCI 命令实现
 */
#include "bt_hci.h"
#include "h4_complete.h"

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
static h4_complete_parser s_parser;

static int hook_rx(uint8_t *buf, uint16_t len)
{
    if (s_armed && buf) {
        h4_complete_feed(&s_parser, buf, len);
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
    h4_complete_init(&s_parser, opcode);
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
    for (int spin = 0; spin < 3000 && !s_parser.found; spin++) {
        busy_wait(3000);
    }

    /* 4) 恢复原指针 */
    s_armed = 0;
    *(volatile uint32_t *)s_slot = (uint32_t)s_orig_rx;

    if (!s_parser.found)
        return BT_ERR_TIMEOUT;
    if (status) *status = s_parser.status;
    if (s_parser.status)
        return BT_ERR_STATUS;

    if (out && outmax > 0) {
        int n = (int)s_parser.result_length < outmax ? (int)s_parser.result_length : outmax;
        for (int i = 0; i < n; i++)
            out[i] = s_parser.event[i+4];
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
