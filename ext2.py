#! /usr/bin/env python
#encoding=utf8

__author__ = 'dmytrish'
__version__ = '0.1'

"""
This is a collection of low-level classes for inspecting ext2
internals. In order to use it effectively you need understanding
the ext2 data layout. The main goal of this tool is to be a tool
for manual manipulation on an ext2 filesystem (possibly broken or
nonstandard).

Class ext2fs tries to provide user-friendly and abstract interface to
filesystem manipulation routines.
How to start (see ext2.ext2fs.__doc__ for details):

>>> import ext2
>>> e2 = ext2.ext2fs( '/path/to/ext2/image/or/device' )

Getting information about FS:
>>> print e2.sb       # this is the superblock information
>>> print e2.space_bytes(), e2.free_space_bytes()
>>> print e2.sb.uuid, e2.sb.name

List a directory on the FS:
>>> print e2.ls('')  # root directory of the FS
>>> print e2.ls('/') # the same
>>> print e2.ls('linux/fs/ext2')
>>> print e2.ls('/boot/grub')

Copy file to and fro:
>>> e2.pull('boot/grub/menu.lst', '.')
>>> e2.push('~/code/py/ext2', '/src/')

(l) License: beerware.
You use this script at your own peril and must not moan for its speed.
"""

import struct
import stat
import time
import uuid
import os

stat_full_rights = 'rwxrwxrwx'
stat_filetype = {
    stat.S_IFDIR: 'd', stat.S_IFREG: '-', stat.S_IFLNK: 'l',
    stat.S_IFCHR: 'c', stat.S_IFBLK: 'b', stat.S_IFSOCK: 's',
    stat.S_IFIFO: 'p' }

struct.intsz = struct.calcsize('I')


def unpack_struct(fmt, strct, s):
    val_tuple = struct.unpack( fmt, s[:struct.calcsize(fmt)] )
    return dict( zip(strct, val_tuple) )

def unpack_int_at(s, index):
    return struct.unpack_from('1I', s, index * struct.intsz)[0]

def time_format(unix_time):
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(unix_time))

class Ext2Exception(Exception):
    def __init__(self, msg):
        self.msg = msg
    def __str__(self):
        return self.msg

class E2IO:
    def __init__(self, source):
        self.f = open(source)
        # self.blksz must be read from the file, so setting it later:

    def set_blksz(self, blksz):
        self.blksz = blksz

    def close(self):
        self.f.close()

    def read_block(self, block_num):
        self._go_to_block(block_num)
        return self.f.read(self.blksz)

    def read(self, count):
        return self.f.read(count)

    def read_at(self, count, offset=0, whence=os.SEEK_SET):
        self.f.seek(offset, whence)
        return self.f.read(count)

    def lock(self): pass   # TODO: add muteces here
    def unlock(self): pass

    def _go_to_block(self, block_num):
        self.f.seek(block_num * self.blksz)


class e2dentry:
    d_fmt = 'IHBB'
    fmt_size = struct.calcsize(d_fmt)
    d_flds = ('d_inode', 'd_entry_size', 'd_namelen', 'd_filetype' )
    stattype = [ 0, stat.S_IFREG, stat.S_IFDIR, stat.S_IFCHR,
                 stat.S_IFBLK, stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFLNK ]

    def __init__(self, io, offset):
        io.lock()
        byte_array = io.read_at( self.fmt_size, offset )
        self.d = unpack_struct(self.d_fmt, self.d_flds, byte_array)
        self.inode = self.d['d_inode']

        raw_name_size = self.d['d_entry_size'] - struct.calcsize(self.d_fmt)
        raw_name = io.read( raw_name_size )
        io.unlock()
        self.name = struct.unpack(str(raw_name_size) + 's', raw_name)[0]
        self.name = self.name.strip('\0')[ : self.d['d_namelen'] ]

        try: self.ftype = self.stattype[ self.d['d_filetype'] ]
        except KeyError:
            raise Ext2Exception(
                'Invalid file type %d for dentry %s' % (e.ftype, e.name))


class e2directory:
    def __init__(self, io, inode):
        if not inode.is_directory():
            raise Ext2Exception('Not a directory: ' % inode.name)
        ## TODO: directory might be more than 1 block
        self.ent = []
        bytes_read = 0
        while bytes_read < io.blksz:
            offset = (inode.d['i_db0'] * io.blksz) + bytes_read
            e = e2dentry(io, offset)
            self.ent.append( e )
            bytes_read += e.d['d_entry_size']

    def ent_by_name(self, name):
        for e in self.ent:
            if e.name == name: return e
        return None

    def ls(self):
        for e in self.ent:
            line = stat_filetype[ e.ftype ]
            line += '\t' + str(e.inode)
            line += '\t' + e.name
            print line


class e2inode:
    i_fmt = '2H5I2H3I12I3I'
    i_flds = (
        'i_mode',   'i_uid',    'i_size',
        # time
        'i_atime',  'i_ctime',  'i_mtime',  'i_dtime',
        'i_gid',    'i_links_count',    'i_blocks',
        'i_flags',  'i_osspec1',
        # direct block pointers
        'i_db0', 'i_db1', 'i_db2', 'i_db3', 'i_db4', 'i_db5',
            'i_db6', 'i_db7', 'i_db8', 'i_db9', 'i_db10', 'i_db11',
        # single-, double-, tripple- indirect block pointers
        'i_i1b', 'i_i2b', 'i_i3b' )
    EXT2_NDIR_BLOCKS = 12
    EXT2_N_BLOCKS = 15

    def __init__(self, io, offset, inosz):
        self.i_size = inosz
        byte_array = io.read_at(self.i_size, offset)
        self.d = unpack_struct(self.i_fmt, self.i_flds, byte_array)

        self.uid = self.d['i_uid']
        self.gid = self.d['i_gid']
        self.n_length = self.d['i_size']
        self.mode = self.d['i_mode']
        self.nlink = self.d['i_links_count']

        if not self.is_short_link():
            self.block_list = self._build_block_list(io)

    def _build_block_list(self, io):
        ''' return list of absolute block addresses for the inode '''
        def list_of_indirects(ib):
            bl = []
            for i in xrange( io.blksz / struct.intsz ):
                bn = unpack_int_at(ib, i)
                if bn is 0: return bl
                bl.append(bn)
            return bl

        def list_of_double_indirects(self, dib):
            dibl = []
            for i in xrange( io.blksz / struct.intsz ):
                ibn = unpack_int_at(dib, i)
                if ibn is 0: return dibl
                ib = io.read_block(ibn)
                dibl.extend( list_of_indirects(ib) )
            return dibl

        blocks = []
        for i in range( e2inode.EXT2_NDIR_BLOCKS ):
            block_num = self.d['i_db' + str(i)]
            if block_num == 0: return blocks
            blocks.append(block_num)

        i1b_num = self.d['i_i1b']
        if i1b_num is 0: return blocks
        i1b = io.read_block(i1b_num)
        blocks.extend( list_of_indirects(i1b) )

        i2b_num = self.d['i_i2b']
        if i2b_num is 0: return blocks
        i2b = io.read_block(i2b_num)
        blocks.extend( list_of_double_indirects(i2b) )

        i3b_num = self.d['i_i3b']
        if i3b_num is 0: return blocks
        i3b = io.read_block(i3b_num)
        for i in xrange( io.blksz / struct.intsz ):
            dibn = unpack_int_at(i3b, i)
            if dibn is 0: return blocks
            dib = io.read_block(dibn)
            blocks.extend( list_of_double_indirects(dib) )

        print 'it''s kinda strange to reach this point, is the inode really that long?'
        return blocks

    def get_mode(self):
        rights = ''
        for i in range(9):
            if (1 << (8 - i)) & self.mode:
                rights += stat_full_rights[i]
            else: rights += '-'
        return stat_filetype[ stat.S_IFMT(self.mode) ] + rights

    def is_directory(self):
        return stat.S_IFMT(self.mode) == stat.S_IFDIR

    def is_device(self):
        return stat.S_IFMT(self.mode) in (stat.S_IFCHR, stat.S_IFBLK)

    def is_link(self):
        return stat.S_IFMT(self.mode) == stat.S_IFLNK

    def is_short_link(self):
        return self.is_link() and self.n_length <= struct.intsz * self.EXT2_N_BLOCKS

    def block_at(self, fileblock):
        ''' absolute block number from relative in-file block number '''
        return self.block_list[fileblock]

    def get_block_list(self):
        return self.block_list

    def blocks_as_string(self):
        """ this method is used for reading in-place links, up to 60 chars """
        s = ''
        for i in range( e2inode.EXT2_N_BLOCKS ):
            if i < e2inode.EXT2_NDIR_BLOCKS:
                b = self.d['i_db' + str(i)]
            else:
                b = self.d['i_i%db' % (1 + i - e2inode.EXT2_NDIR_BLOCKS)]
            if b == 0: break
            s += struct.pack('I', b)
        return s.strip('\0')

    def device_id(self):
        dev = self.d['i_db0']
        return (os.major(dev), os.minor(dev))

    def __str__(self):
        res = self.get_mode()
        res += ' %3d' % self.d['i_links_count']
        res += ' %4d:%d\t' % (self.uid, self.gid)
        if self.is_device():  # devices need DevID formatting
            res += '     (%2d,%2d)' % self.device_id()
        else:
            res += ' %10d' % self.n_length
        res += ' %s' % time_format(self.d['i_ctime'])
        return res


class e2group_descriptor:
    gd_size = 32
    gd_fmt = '3I3H'
    gd_flds = (
        'bg_block_bitmap',      'bg_inode_bitmap',      'bg_inode_table',
        'bg_free_blocks_count', 'bg_free_inodes_count', 'bg_used_dirs_count' )

    def check_range(self, x, description):
        if not ( (self.start <= x) and (x < self.end) ):
            raise Ext2Exception('Bad %s block %d for block_group_desc[%d]' %
                (description, x, self.index))

    def check(self):
        self.check_range(self.block_bitmap, 'blockbitmap')
        self.check_range(self.inode_bitmap, 'inodebitmap')
        self.check_range(self.inode_table, 'inodetable')

    def __init__(self, fs, offset, index):
        self.index = index
        byte_array = fs.io.read_at(self.gd_size, offset + index * self.gd_size)
        self.d = unpack_struct(self.gd_fmt, self.gd_flds, byte_array)
        self.block_bitmap = self.d['bg_block_bitmap']
        self.inode_bitmap = self.d['bg_inode_bitmap']
        self.inode_table = self.d['bg_inode_table']

        self.start = fs.sb.boot_block + self.index * fs.sb.blocks_in_grp
        self.end = self.start + fs.sb.blocks_in_grp

        self.check()


class e2superblock:
    file_offset = 1024
    sb_size = 1024
    ext2magic = 0xef53
    root_dir_inode = 2
    sb_fmt = '13I6H4I2HI2H3I16s16s64sI2B'
    sb_keys = (
        's_inodes_count',       's_blocks_count',           's_r_blocks_count',
        's_free_blocks_count',  's_free_inodes_count',      's_first_data_block',
        's_log_block_size',     's_log_frag_size',          's_blocks_per_group',
        's_frags_per_group',    's_inodes_per_group',       's_mtime',
        's_wtime',              's_mnt_count',              's_max_mnt_count',
        's_magic',              's_state',                  's_errors',
        's_minor_rev_level',    's_lastcheck',              's_checkinterval',
        's_creator_os',         's_rev_level',              's_def_resuid',
        's_def_resgid',         's_first_ino',              's_inode_size',
        's_block_group_nr',     's_feature_compat',         's_feature_incompat',
        's_feature_ro_compat',  's_uuid',                   's_volume_name',
        's_last_mounted',       's_algorithm_usage_bitmap', 's_prealloc_block',
        's_prealloc_dir_blocks' )

    def __init__(self, io):
        byte_array = io.read_at( self.sb_size, self.file_offset )
        self.d = unpack_struct(self.sb_fmt, self.sb_keys, byte_array)
        if self.d['s_magic'] != self.ext2magic:
            raise Ext2Exception('Invalid ext2 superblock: the magic is bad')

        self.blksz = 1024 << self.d['s_log_block_size']
        io.set_blksz(self.blksz)
        self.n_inodes = self.d['s_inodes_count']
        self.n_blocks = self.d['s_blocks_count']
        self.n_free_inodes = self.d['s_free_inodes_count']
        self.n_free_blocks = self.d['s_free_blocks_count']
        self.blocks_in_grp = self.d['s_blocks_per_group']
        self.inodes_in_grp = self.d['s_inodes_per_group']
        self.boot_block = self.d['s_first_data_block']
        self.name = str( self.d['s_volume_name']).strip('\0' )
        self.uuid = str( uuid.UUID(bytes = self.d['s_uuid']) )

        self.check()

    def check(self):
        pass

    def __str__(self):
        res = ''
        for k in self.d:
            v = str(self.d[k])
            if k == 's_uuid':
                v = self.uuid
            elif k in ('s_lastcheck', 's_wtime'):
                v = time_format(self.d[k])
            res += ('%s = %s\n' % (k, v))
        return res

    def block_size(self):
        return self.blksz

    def inode_size(self):
        if self.d['s_rev_level'] > 0: return self.d['s_inode_size']
        else: return 128


class ext2fs:
    """ an ext2fs object represents a mounted ext2 file system.
    """
    def __init__(self, filename):
        self.io = E2IO(filename)
        self.sb = e2superblock(self.io)

        self._blksz = self.sb.block_size()
        self._indsz = self.sb.inode_size()

        self._bgd = self._blkgrps_read()
        self.root = self._inode(self.sb.root_dir_inode)

    def umount(self):
        self.io.close()

    def _blkgrps_read(self):
        self._n_blkgrps = self.sb.n_blocks / self.sb.blocks_in_grp
        if self.sb.n_blocks % self.sb.blocks_in_grp: self._n_blkgrps += 1

        offset = (1 + self.sb.boot_block) * self._blksz
        bgd = []
        for i in range( self._n_blkgrps ):
            bgd.append( e2group_descriptor(self, offset, i) )
        return bgd

    def _inode(self, ino_num):
        """ construct and read e2inode for index #ino_num"""
        group_index = (ino_num - 1) % self.sb.inodes_in_grp
        bg = self._bgd[ (ino_num - 1) / self.sb.inodes_in_grp ]
        offset =  bg.inode_table * self._blksz   # go to inode table
        offset += group_index * self._indsz
        return e2inode(self.io, offset, self._indsz)

    def _ent_by_path(self, pathto):
        if pathto == '/':
            return e2directory(self.io, self.root).ent_by_name('.')

        path_array = pathto.split('/')
        while path_array.count(''): path_array.remove('')

        inode = self.root
        dentry = None
        for fname in path_array:
            dentry = e2directory(self.io, inode).ent_by_name(fname)
            if dentry is None:
                raise Ext2Exception(
                    'Name lookup failed for "%s" in "%s"' % (fname, pathto))
            inode = self._inode(dentry.inode)
        return dentry

    def _inode_by_path(self, pathto):
        """ return e2inode for path 'pathto' """
        if pathto == '/':
            return self.root

        path_array = pathto.split('/')
        while path_array.count(''): path_array.remove('')

        inode = self.root
        for fname in path_array:
            dentry = e2directory(self.io, inode).ent_by_name(fname)
            if dentry is None:
                raise Ext2Exception(
                    'Name lookup failed for "%s" in "%s"' % (fname, pathto))
            inode = self._inode(dentry.inode)
        return inode

    def _dir_by_inode(self, ino_num):
        return e2directory(self.io, self._inode(ino_num))

    def free_space_bytes(self):
        return self.sb.n_free_blocks * self._blksz

    def space_bytes(self):
        return self.sb.n_blocks * self._blksz

    def ls(self, pathname, opts=''):
        """ lists files in 'pathname' like 'ls -l'
            The second argument controls listing format, options:
            'i' - output inodes, e.g. fs.ls('dir/subdir', 'i')
        """
        def print_dentry(dentry):
            if opts.count('i'):
                print self._inode(e.inode), '%8d' % e.inode, e.name
            else: print self._inode(e.inode), e.name

        inode = self._inode_by_path(pathname)
        if inode.is_directory():
            d = e2directory(self.io, inode)
            for e in d.ent: print_dentry(e)
        else:
            print inode

    def pull(self, fspath, to_file):
        """ copy file from ext2 image at 'fspath' to external file 'to_file' """
        inode = self._inode_by_path(fspath)
        try:
            st = os.stat(to_file)
            if stat.S_IFDIR == stat.S_IFMT(st.st_mode):
                to_file += '/' + fspath.split('/')[-1]
        except OSError: pass

        bytes_written = 0
        destination = open(to_file, 'w')
        for block in inode.get_block_list():
            bytes_to_copy = min(inode.n_length - bytes_written, self._blksz)
            if bytes_to_copy <= 0:
                destination.close()
                os.remove(to_file)
                raise Ext2Exception('Redundant blocks in file %s' % path)
            piece = self.io.read_block(block)[:bytes_to_copy]
            destination.write( piece )
            bytes_written += bytes_to_copy
        destination.close()

    def read(self, fspath, offset, bytes_count):
        if bytes_count <= 0 or offset < 0: return ''

        inode = self._inode_by_path(fspath)

        end_offset = offset + bytes_count
        if end_offset > inode.n_length:
            end_offset = inode.n_length
            bytes_count = inode.n_length - offset

        start_fileblock = offset / self._blksz
        end_fileblock = (end_offset - 1) / self._blksz

        start_block_offset = offset % self._blksz
        start_block = inode.block_at(start_fileblock)
        contents = self.io.read_block( start_block )[start_block_offset:]
        if start_block_offset + bytes_count <= self._blksz:
            return contents[:bytes_count]

        for i in range(start_fileblock + 1, end_fileblock):
            block_contents = self.io.read_block( inode.block_at(i) )
            contents += block_contents

        end_block_bytes = end_offset % self._blksz
        if end_block_bytes is 0: end_block_bytes = self._blksz
        end_block = inode.block_at(end_fileblock)
        end_contents = self.io.read_block( end_block )[:end_block_bytes]
        contents += end_contents

        return contents

    def readlink(self, path):
        inode = self._inode_by_path(path)
        if inode.is_short_link(): # in-place link, less than or equal to 60 characters
            return inode.blocks_as_string()
        #else: long link with its own blocks
        s = ''
        for b in inode.get_block_list():
            sb = self.io.read_block(b)
            s += sb.split('\0')[0]
            if sb.count('\0'): break
        return s

    def push(self, from_file, to_fspath):
        """ write an external file 'from_file' to ext2 path 'fspath' """
        ### TODO
        pass

def usage():
    print 'Usage: %s /path/to/ext2/img/or/device> <action>' % sys.argv[0]
    print '<action>s:'
    print '   info'
    print '   ls <path>'
    print '   cp <from/image> <outside/file>'

if '__main__' == __name__:
    import sys
    if len(sys.argv) < 3:
        usage()
        sys.exit(-1)

    imgfile = sys.argv[1]
    try: 
        e2fs = ext2fs(imgfile)
    except IOError:
        print 'No such file: %s' % imgfile
        sys.exit(-2)

    if sys.argv[2] == 'info':
        if e2fs.sb.d['s_state'] > 1: print 'State: %d' % e2fs.sb.d['s_state']
        print('UUID: %s, Label: "%s"' % (e2fs.sb.uuid.__str__, e2fs.sb.name))
        print('Total space: %d, free space: %d bytes' % (e2fs.space_bytes(), e2fs.free_space_bytes()))
        print('Block size: %d' % e2fs.sb.block_size())
        print('Total inodes: %d, free inodes: %d' % (e2fs.sb.n_inodes, e2fs.sb.n_free_inodes))
        print('Last mounted: %s' % time_format(e2fs.sb.d['s_last_mounted']))
        print('Mounted %d times without check, checked every %d time' % (e2fs.sb.d['s_mnt_count'], e2fs.sb.d['s_max_mnt_count']))
        print('last checked %s, check interval is %d' % (time_format(e2fs.sb.d['s_lastcheck']), time_format(e2fs.sb.d['s_checkinterval'])))
        print('')
    elif sys.argv[2] == 'ls':
        if len(sys.argv) < 4: usage()
        else: e2fs.ls(sys.argv[3])
    elif sys.argv[2] == 'cp':
        if len(sys.argv) < 5: usage()
        else: e2fs.pull(sys.argv[3], sys.argv[4])
    else: usage()

