#!/usr/bin/env python

import fuse
import errno
import sys

from ext2 import *

fuse.fuse_python_api = (0, 2)

usage = '''
ext2 fuse filesystem
Usage: 
$ e2fuse.py <image/file> <mount/dir>
''' + fuse.Fuse.fusage

class e2fuse(fuse.Fuse):
    def __init__(self, *args, **kw):
        fuse.Fuse.__init__(self, *args, **kw)
        self.ro = True
        print args, kw

        try:
            self.fs = ext2fs(self.mountee)
        except Exception:
            print 'e2fuse() failed'
        
    def getattr(self, path):
        try: ent = self.fs._ent_by_path(path)
        except Ext2Exception(e):
            return -errno.ENOENT
        
        ino = self.fs._inode(ent.inode)
        st = fuse.Stat()
    
        st.st_atime = ino.d['i_atime']
        st.st_ctime = ino.d['i_ctime']
        st.st_mtime = ino.d['i_mtime']

        st.st_ino = ent.inode
        st.st_uid = ino.uid
        st.st_gid = ino.gid
        st.st_mode = ino.mode
        st.st_nlink = ino.nlink
        st.st_size = ino.n_length
        st.st_dev = 0
        return st 

    def readdir(self, path, offset):
        dirents = [ '.', '..' ]
        try: dir_ino = self.fs._inode_by_path(path)
        except Ext2Exception(e):
             yield -errno.ENOENT

        try: dirent = self.fs._dir_by_inode(dir_ino)
        except Ext2Exception(e): 
            yield -errno.ENOTDIR

        for de in dirent.ent:
            dirents.append(de.name)
        
        for r in dirents:
            yield fuse.Direntry(r)

    def mknod(self, path, mode, dev):
        if self.ro: return -errno.EROFS
        return -errno.ENOSYS

    def unlink(self, path):
        if self.ro: return -errno.EROFS
        return -errno.ENOSYS

    def read(self, path, size, offset):
        return -errno.ENOSYS

    def write(self, path, buf, offset):
        if self.ro: return -errno.EROFS
        return -errno.ENOSYS

    def release(self, path, flags):
        return -errno.ENOSYS

    def open(self, path, flags):
        return -errno.ENOSYS

    def truncate(self, path, size):
        if self.ro: return -errno.EROFS
        return -errno.ENOSYS

    def utime(self, path, times):
        return -errno.ENOSYS

    def mkdir(self, path, mode):
        if self.ro: return -errno.EROFS
        return -errno.ENOSYS

    def rmdir(self, path):
        if self.ro: return -errno.EROFS
        return -errno.ENOSYS

    def rename(self, pathfrom, pathto):
        if self.ro: return -errno.EROFS
        return -errno.ENOSYS

    def fsync(self, path, isfsyncfile):
        if self.ro: return -errno.EROFS
        return -errno.ENOSYS

    def symlink(self, target, name):
        if self.ro: return -errno.EROFS
        return -errno.ENOSYS

    def readlink(self, path):
        return self.fs.readlink(path)


def main(argv):
    fsserv = e2fuse(version="%prog " + fuse.__version__, usage=usage, dash_s_do='setsingle')
    fsserv.parser.add_option(default='/', mountopt='root', help='')
    fsserv.parse(errex=1)
    try: print fsserv.fuse_args.mount_expected()
    except OSError:
        print >> sys.stderr, "Mount expected failed"
        sys.exit(-1)
    fsserv.main()

if __name__ == '__main__':
    main(sys.argv)
