"""Create a nonce-tagged, one-command request for bthcirequestprobe."""
import argparse
import secrets
from pathlib import Path
from nanodbg.hci import encode_request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('opcode', help='HCI opcode as hexadecimal, for example 0x200b')
    parser.add_argument('params', help='parameter bytes as hexadecimal; use an empty string for none')
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    opcode = int(args.opcode, 16)
    params = bytes.fromhex(args.params)
    nonce = secrets.token_bytes(4)
    args.output.write_bytes(encode_request(opcode, params, nonce))
    print(f'nonce={nonce.hex()} opcode=0x{opcode:04x} params={params.hex()}')


if __name__ == '__main__':
    main()
