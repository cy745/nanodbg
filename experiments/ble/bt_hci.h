/*
 * bt_hci.h — 同步 HCI 命令 API（第一版，基于实机验证）
 *
 * 已实机验证 HCI_Read_BD_ADDR，匹配 Command Complete。
 *
 * 机制：
 *   1. 传输接口对象 obj = *(0x0895C134)（蓝牙关时是静态桩表）
 *   2. obj+0x18 = send(type, opcode, plen)
 *   3. obj+0x20 = rx_feed(uint8_t *buf, uint16_t len)  ← 接收解析喂入点
 *   4. 临时把 +0x20 换成自己的钩子，抄下入站字节后原样转发
 *   5. 轮询匹配 Command Complete(opcode)，超时则放弃
 *   6. 无论成败都恢复原指针
 *
 * 注意：钩子是临时的；调用期间不要切走应用（应用卸载会释放本代码内存）。
 */
#ifndef BT_HCI_H_
#define BT_HCI_H_

#include <stdint.h>
#include <stdbool.h>

#define BT_TRANSPORT_SLOT   0x0895C134u
#define BT_STUB_TABLE       0x0895C100u
#define BT_STUB_SEND        0x080EF0C4u
#define BT_HCI_CTX          0x0896DD18u
#define BT_HCI_SEND_THUNK   0x080F6AF4u
#define BT_HCI_SEND_STAGED  0x080F72C8u
#define BT_SLOT_SEND        0x18u
#define BT_SLOT_RX          0x20u

/* 返回码 */
#define BT_OK               0
#define BT_ERR_OFF         -1    /* 蓝牙未开 */
#define BT_ERR_NO_TRANSPORT -2
#define BT_ERR_TIMEOUT     -3    /* 没等到 Command Complete */
#define BT_ERR_STATUS      -4    /* 控制器返回非 0 状态；用 bt_hci_cmd_status 获取 */
#define BT_ERR_SHORT       -5
#define BT_ERR_ARGUMENT    -6    /* 参数长度非零但指针为空 */

/* 常用命令 */
#define BT_OP_READ_LOCAL_VERSION  0x1001
#define BT_OP_READ_LOCAL_COMMANDS 0x1002
#define BT_OP_READ_LOCAL_FEATURES 0x1003
#define BT_OP_READ_BUFFER_SIZE    0x1005
#define BT_OP_READ_BD_ADDR        0x1009
#define BT_OP_READ_LOCAL_NAME     0x0C14
#define BT_OP_READ_CLASS_OF_DEV   0x0C23
#define BT_OP_LE_SET_SCAN_PARAMS  0x200B
#define BT_OP_LE_SET_SCAN_ENABLE  0x200C

/* 蓝牙是否已就绪 */
bool bt_is_on(void);

/* 传输层接收喂入函数类型（obj+0x20），需要自己装钩子时用 */
typedef int (*rx_feed_t)(uint8_t *buf, uint16_t len);

/* 同步执行一条 HCI 命令。
 *   params/plen : 命令参数（plen=0 时可为 NULL）
 *   out/outmax  : 接收 Command Complete 的参数区（status 之后的部分）
 * 单次只允许一个命令在途，且调用期间不能切走应用。返回 BT_OK / 负错误码；
 * 返回成功时 *outlen 为写入 out 的字节数。 */
int bt_hci_cmd(uint16_t opcode, const void *params, uint8_t plen,
               uint8_t *out, int outmax, int *outlen);

/* 如收到匹配的 Command Complete，将 HCI 状态写入 status；未收到时为 0xff。 */
int bt_hci_cmd_status(uint16_t opcode, const void *params, uint8_t plen,
                      uint8_t *out, int outmax, int *outlen, uint8_t *status);

/* Accept either immediate response. A successful Command Status only means
 * the operation started; its later completion is not captured by this API. */
int bt_hci_cmd_ack(uint16_t opcode, const void *params, uint8_t plen,
                   uint8_t *out, int outmax, int *outlen, uint8_t *status,
                   uint8_t *response_event);

/* 便捷封装 */
int bt_read_bd_addr(uint8_t addr[6]);
int bt_read_local_name(char name[248]);

#endif /* BT_HCI_H_ */
