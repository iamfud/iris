import struct

with open(r'C:\Users\fudne\AppData\Roaming\OpenRGB\Red.orp', 'rb') as f:
    data = f.read()

print(f'Total size: {len(data)} bytes')
print('Header:', data[:20].hex())
print('  Magic:', data[:16])
print('  Version:', struct.unpack('I', data[16:20])[0])

pos = 20
ctrl_idx = 0
while pos < len(data):
    if pos + 4 > len(data):
        break
    size = struct.unpack('I', data[pos:pos+4])[0]
    print(f'\nController {ctrl_idx}: size_field={size}, pos={pos}')
    if size < 4 or size > 1000000:
        print(f'  Unexpected size, breaking')
        break
    chunk = data[pos:pos+size]
    print(f'  First 64 bytes of chunk: {chunk[:64].hex()}')
    if len(chunk) > 64:
        print(f'  Last 32 bytes of chunk: {chunk[-32:].hex()}')
    pos += size
    ctrl_idx += 1
    if ctrl_idx > 10:
        break

print(f'\nRemaining bytes after last controller: {len(data) - pos}')
