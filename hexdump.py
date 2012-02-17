import string

bytes_per_line = 16
bytes_per_block = 4
nonprintable = '.'

addr_format = '%8x : '
byte_format = '%2x '
byte_fmt_len = 3

def hexdump(raw_string, start_at=0):
    i = start_at
    s = ''
    asc = ''
    
    # from the first line
    initial_offset = (start_at % bytes_per_line)
    if initial_offset: 
        offset = byte_fmt_len * initial_offset
        offset += initial_offset / bytes_per_block
        if initial_offset % bytes_per_block: offset += 1
        s = ' ' * offset
        asc = ' ' * initial_offset
    
    for b in raw_string:
        if 0 == i % bytes_per_block: s += ' '
        s += '%02x ' % ord(b)

        if b in string.printable: asc += b
        else: asc += nonprintable

        i += 1

        if 0 == i % bytes_per_line and i > start_at:
            s += '| ' + asc
            print (addr_format % (i - bytes_per_line)) + s
            s = ''
            asc = ''
    
    finish_offset = i % bytes_per_line
    if finish_offset:
        offset = byte_fmt_len * (bytes_per_line - finish_offset)
        offset += (bytes_per_line - finish_offset) / bytes_per_block
        s += ' ' * offset
        print (addr_format % (i - finish_offset)) + s + '| ' + asc
