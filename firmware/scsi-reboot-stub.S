/* Experimental nano 7G 39A10023 C6 handler. 88-byte publisher slot.
 * sub 2: existing 512-byte arbitrary read; sub 0xa7: call the ARM/Thumb address
 * in CDB[3..6] with r0 = 0x7ffffff0 (the existing panic-allocation probe).
 * This is a crash-based experiment, not a graceful reboot API.
 */
.syntax unified
.thumb
.text
.global scsi_reboot_stub
.thumb_func
scsi_reboot_stub:
    push {r1-r7, lr}
    mov r4, r2
    mov r5, r0
    movs r6, #0
    str r6, [r0]
    ldr r0, [r2]
    ldr r1, [r0, #8]
    mov r0, r2
    blx r1
    ldrb r6, [r0, #2]
    cmp r6, #2
    beq 1f
    cmp r6, #0xa7
    bne 3f
1:
    ldrb r2, [r0, #3]
    ldr r3, [r0, #4]
    lsls r2, r2, #24
    rev r3, r3
    lsrs r3, r3, #8
    orrs r2, r3
    cmp r6, #0xa7
    bne 2f
    movs r0, #31
    mvns r0, r0
    lsrs r0, r0, #1
    blx r2
3:
    movs r0, #0x70
    strb r0, [r5]
    pop {r1-r7, pc}
2:
    mov r0, r2
    str r2, [sp, #4]
    movs r1, #1
    lsls r1, r1, #9
    str r1, [sp, #8]
    movs r2, #7
    mov ip, r2
    svc #70
    ldr r1, [sp, #8]
    ldr r0, [r4]
    ldr r3, [r0, #16]
    add r2, sp, #4
    mov r0, r4
    blx r3
    pop {r1-r7, pc}
    .ltorg
