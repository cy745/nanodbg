# Experimental device-side work

`experimental-upstream.patch` records local modifications against commit
`7a0f097` of [nano7-untethered](https://github.com/olievans123/nano7-untethered).
It includes experiments for the resident debugger, autostart and Bluetooth,
as well as bootstrap/publisher changes. See `UPSTREAM-LICENSE.txt` for the
upstream notices. `scsi-reboot-stub.S` is the experimental C6 command handler.

This is a research snapshot, not a complete reproducible firmware build or
installation procedure. The specific firmware image, build recipe, deployment
procedure and interaction between changes still need to be documented and
independently validated. Do not assume applying the patch alone produces a
compatible image. No Apple firmware or device data is distributed here.
