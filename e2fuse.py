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
        self.logfile = open('/tmp/e2fuse.log', 'w')
        self.log('Starting e2fuse...')
        print args, kw
        try:
            self.fs = ext2fs('/home/mithra/code/cosec/cosec.img')
            self.log('mounted successfully')
        except Exception:
            self.log('e2fuse() failed');
       
    def log(self, msg):
        self.logfile.write(msg + '\n')
        
    def getattr(self, path):
        self.log('getattr("%s")' % path)
        try: ent = self.fs._ent_by_path(path)
        except Ext2Exception:
            self.log('getattr: failed to find %s' % path)
            return -errno.ENOENT
        
        self.log('getattr inode = %d', ent.inode)
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
        self.log('getattr: ino = %d' % ino)
        #self.log('getattr info: ' + .__str__)
        return st 

    def readdir(self, path, offset):
        self.log('readdir("%s")' % path)
        dirents = [ '.', '..' ]
        try: dir_ino = self.fs._inode_by_path(path)
        except Ext2Exception(e):
             self.log('readdir: No inode for path')
             yield -errno.ENOENT

        try: d = e2directory(self.fs, dir_ino)
        except Ext2Exception(e): 
            self.log('readdir: inode is not a directory')
            yield -errno.ENOTDIR

        for de in d.ent:
            dirents.append(de.name)
        
        for r in dirents:
            yield fuse.Direntry(r)

    def mknod(self, path, mode, dev):
        self.log('mknod("%s", %o, %d")' % (path, mode, dev))
        if self.ro: return -errno.EROFS
        return -errno.ENOSYS

    def unlink(self, path):
        self.log('unlink("%s")' % path)
        if self.ro: return -errno.EROFS
        return -errno.ENOSYS

    def read(self, path, size, offset):
        self.log('read(%s, %d, %d)' % (path, size, offset))
        return -errno.ENOSYS

    def write(self, path, buf, offset):
        self.log('write(%s, %d, %d)' % (path, len(buf), offset))
        if self.ro: return -errno.EROFS
        return -errno.ENOSYS

    def release(self, path, flags):
        return -errno.ENOSYS

    def open(self, path, flags):
        self.log('open(%s)' % path)
        return -errno.ENOSYS

    def truncate(self, path, size):
        self.log('truncate(%s, %d)' % (path, size))
        if self.ro: return -errno.EROFS
        return -errno.ENOSYS

    def utime(self, path, times):
        return -errno.ENOSYS

    def mkdir(self, path, mode):
        self.log('mkdir(%s)' % path)
        if self.ro: return -errno.EROFS
        return -errno.ENOSYS

    def rmdir(self, path):
        self.log('rmdir(%s)' % path)
        if self.ro: return -errno.EROFS
        return -errno.ENOSYS

    def rename(self, pathfrom, pathto):
        self.log('rename(%s, %s)' % (pathfrom, pathto))
        if self.ro: return -errno.EROFS
        return -errno.ENOSYS

    def fsync(self, path, isfsyncfile):
        self.log('fsync(%s)' % path)
        if self.ro: return -errno.EROFS
        return -errno.ENOSYS

    def symlink(self, target, name):
        if self.ro: return -errno.EROFS
        return -errno.ENOSYS

    def readlink(self, path):
        link = self.fs.readlink(path)
        self.log('readlink("%s") = %s' % (path, link))
        return link

    def statvfs(self):
        self.log('statvfs()')
        return -errno.ENOSYS
        
    def statfs(self, path):
        self.log('statfs(%s)' % path)
        return -errno.ENOSYS


def main(argv):
    fsserv = e2fuse(version="%prog " + fuse.__version__, usage=usage, dash_s_do='setsingle')
    fsserv.parser.add_option(mountopt='img', default='', help='set /path/to/ext2/image')
    fsserv.parse(values=fsserv, errex=1)
    try: print fsserv.fuse_args.mount_expected()
    except OSError:
        print >> sys.stderr, "Mount expected failed"
        sys.exit(-1)
    fsserv.main()

if __name__ == '__main__':
    main(sys.argv)
