#!/usr/bin/env python

import sys
import json
import hashlib

def get_message():
    raw_length = sys.stdin.read(4)
    if len(raw_length) == 0:
        sys.exit(0)
    message_length = int.from_bytes(raw_length.encode('latin-1'), 'little')
    message = sys.stdin.read(message_length)
    return json.loads(message)

def send_message(message):
    encoded_message = json.dumps(message).encode('utf-8')
    sys.stdout.buffer.write(len(encoded_message).to_bytes(4, 'little'))
    sys.stdout.buffer.write(encoded_message)
    sys.stdout.flush()

def calculate_sha256_hash(filepath):
    try:
        with open(filepath, 'rb') as f:
            file_hash = hashlib.sha256()
            while chunk := f.read(8192):
                file_hash.update(chunk)
            return file_hash.hexdigest()
    except Exception as e:
        return {'error': str(e)}

if __name__ == '__main__':
    while True:
        try:
            received_message = get_message()
            if 'filePath' in received_message:
                file_path = received_message['filePath']
                file_hash = calculate_sha256_hash(file_path)
                send_message({'hash': file_hash})
        except Exception as e:
            send_message({'error': str(e)})
            break