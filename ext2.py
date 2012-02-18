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


def unpack_struct(fmt, strct, s):
    val_tuple = struct.unpack( fmt, s[:struct.calcsize(fmt)] )
    return dict( zip(strct, val_tuple) )

def time_format(unix_time):
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(unix_time))

class Ext2Exception(Exception):
    def __init__(self, msg):
        self.msg = msg
    def __str__(self):
        return self.msg

class e2dentry:
    d_fmt = 'IHBB'
    fmt_size = struct.calcsize(d_fmt)
    d_flds = ('d_inode', 'd_entry_size', 'd_namelen', 'd_filetype' )
    stattype = [ 0, stat.S_IFREG, stat.S_IFDIR, stat.S_IFCHR,
                 stat.S_IFBLK, stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFLNK ]

    def __init__(self, fs):
        byte_array = fs.f.read( self.fmt_size )
        self.d = unpack_struct(self.d_fmt, self.d_flds, byte_array)
        self.inode = self.d['d_inode']

        raw_name_size = self.d['d_entry_size'] - struct.calcsize(self.d_fmt)
        raw_name = fs.f.read( raw_name_size )
        self.name = struct.unpack(str(raw_name_size) + 's', raw_name)[0]
        self.name = self.name.strip('\0')[ : self.d['d_namelen'] ]

        try: self.ftype = self.stattype[ self.d['d_filetype'] ]
        except KeyError:
            raise Ext2Exception(
                'Invalid file type %d for dentry %s' % (e.ftype, e.name))


class e2directory:
    def __init__(self, fs, inode):
        if not inode.is_directory():
            raise Ext2Exception('Not a directory: ' % inode.name)
        ## TODO: directory might be more than 1 block
        fs._go_to_block( inode.d['i_db0'])
        self.ent = []
        bytes_read = 0
        while bytes_read < fs._blksz:
            e = e2dentry(fs)
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

    def __init__(self, fs):
        self.i_size = fs._indsz
        byte_array = fs.f.read(self.i_size)
        self.d = unpack_struct(self.i_fmt, self.i_flds, byte_array)
        self.uid = self.d['i_uid']
        self.gid = self.d['i_gid']
        self.n_length = self.d['i_size']
        self.mode = self.d['i_mode']

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

    def blocks_list(self):
        blocks = []
        for i in range( e2inode.EXT2_N_BLOCKS ):
            block_num = self.d['i_db' + str(i)]
            if block_num == 0: return blocks
            blocks.append(block_num)

        return blocks

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

    def __init__(self, fs):
        self.index = (fs.f.tell() % fs._blksz) / self.gd_size
        byte_array = fs.f.read(self.gd_size)
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

    def __init__(self, srcfile):
        srcfile.seek( self.file_offset )
        byte_array = srcfile.read( self.sb_size )
        self.d = unpack_struct(self.sb_fmt, self.sb_keys, byte_array)
        if self.d['s_magic'] != self.ext2magic:
            raise Ext2Exception('Invalid ext2 superblock: the magic is bad')

        self.blksz = 1024 << self.d['s_log_block_size']
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
        self.f = open(filename)
        self.sb = e2superblock(self.f)

        self._blksz = self.sb.block_size()
        self._indsz = self.sb.inode_size()

        self._bgd = self._blkgrps_read()
        self.root = self._inode(self.sb.root_dir_inode)

    def umount(self):
        self.f.close()

    def _go_to_block(self, num):
        self.f.seek(num * self._blksz)

    def _read_block(self, num):
        """ return a raw byte string with content of block #num"""
        self._go_to_block(num)
        return self.f.read(self._blksz)

    def _blkgrps_read(self):
        self._n_blkgrps = self.sb.n_blocks / self.sb.blocks_in_grp
        if self.sb.n_blocks % self.sb.blocks_in_grp: self._n_blkgrps += 1

        self._go_to_block( 1 + self.sb.boot_block )
        bgd = []
        for i in range( self._n_blkgrps ):
            bgd.append( e2group_descriptor(self) )
        return bgd

    def _inode(self, ino_num):
        """ construct and read e2inode for index #ino_num"""
        group_index = (ino_num - 1) % self.sb.inodes_in_grp
        bg = self._bgd[ (ino_num - 1) / self.sb.inodes_in_grp ]
        self.f.seek( bg.inode_table * self._blksz )   # go to inode table
        self.f.seek(self._indsz * group_index, os.SEEK_CUR)  # from there
        return e2inode(self)

    def _ent_by_path(self, pathto):
        path_array = pathto.split('/')
        while path_array.count(''): path_array.remove('')

        inode = self.root
        dentry = None
        for fname in path_array:
            dentry = e2directory(self, inode).ent_by_name(fname)
            if dentry is None:
                raise Ext2Exception(
                    'Name lookup failed for "%s" in "%s"' % (fname, pathto))
            inode = self._inode(dentry.inode)
        return dentry

    def _inode_by_path(self, pathto):
        """ return e2inode for path 'pathto' """
        path_array = pathto.split('/')
        while path_array.count(''): path_array.remove('')

        inode = self.root
        for fname in path_array:
            dentry = e2directory(self, inode).ent_by_name(fname)
            if dentry is None:
                raise Ext2Exception(
                    'Name lookup failed for "%s" in "%s"' % (fname, pathto))
            inode = self._inode(dentry.inode)
        return inode

    def _dir_by_inode(self, ino_num):
        return e2directory(self, self._inode(ino_num))

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
            d = e2directory(self, inode)
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
        for block in inode.blocks_list():
            bytes_to_copy = min(inode.n_length - bytes_written, self._blksz)
            if bytes_to_copy <= 0:
                raise Ext2Exception('Redundant blocks in file %s' % path)
                destination.close()
                os.remove(to_file)
            piece = self._read_block(block)[:bytes_to_copy]
            destination.write( piece )
            bytes_written += bytes_to_copy
        destination.close()

    def readlink(self, path):
        inode = self._inode_by_path(path)
        if inode.n_length <= struct.calcsize('I') * e2inode.EXT2_N_BLOCKS:
            # in-place link, less than or equal to 60 characters
            return inode.blocks_as_string()
        #else: long link with its own blocks
        s = ''
        for b in inode.blocks_list():
            sb = self._read_block(b)
            s += sb.split('\0')[0]
            if sb.count('\0'): break
        return s

    def push_file(self, from_file, to_fspath):
        """ write an external file 'from_file' to ext2 path 'fspath' """
        ### TODO
        pass

if '__main__' == __name__:
    import sys
    if len(sys.argv) < 2:
        print 'Usage: %s /path/to/ext2/img/or/device>' % sys.argv[0]
        sys.exit(-1)

    imgfile = sys.argv[1]
    try: e2fs = ext2fs(imgfile)
    except IOError:
        print 'No such file: %s' % imgfile
        sys.exit(-2)

