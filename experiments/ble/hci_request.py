"""Create a nonce-tagged, one-command request for bthcirequestprobe."""
import argparse
import secrets
from pathlib import Path


def encode_request(opcode, params, nonce):
    if not 0 <= opcode <= 0xffff or len(params) > 255 or len(nonce) != 4:
        raise ValueError('invalid opcode, parameter length, or nonce')
    return b'HCP1' + nonce + opcode.to_bytes(2, 'little') + bytes((len(params),)) + params


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
