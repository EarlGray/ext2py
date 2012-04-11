#!/usr/bin/env python

import os
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
        self.logfile = open('/tmp/e2fuse.log', 'w')
        self.log('Starting e2fuse...')

    def fsinit(self):
        self.ro = self.conf['ro']
        imgf = self.cmdline[1][0]
        if imgf[0] is not '/': imgf = self.cwd + '/' + imgf
        try:
            self.fs = ext2fs(imgf)
            self.log('mounted successfully')
        except Exception:
            self.log('ext2fs(%s) failed' % imgf);
       
    def log(self, msg):
        self.logfile.write(msg + '\n')
        
    def getattr(self, path):
        self.log('getattr("%s")' % path)
        try: ent = self.fs._ent_by_path(path)
        except Ext2Exception:
            self.log('getattr: no "%s"' % path)
            return -errno.ENOENT
        
        self.log('  inode = %d' % ent.inode)
        ino = self.fs._inode(ent.inode)

        st = fuse.Stat()
    
        st.st_atime = ino.d['i_atime']
        st.st_ctime = ino.d['i_ctime']
        st.st_mtime = ino.d['i_mtime']

        st.st_ino = ent.inode
        if self.conf['user']: (st.st_uid, st.st_gid) = (os.getuid(), os.getgid()) 
        else: (st.st_uid, st.st_gid) = (ino.uid, ino.gid)
        st.st_mode = ino.mode
        st.st_nlink = ino.nlink
        st.st_size = ino.n_length
        st.st_dev = 0
        # self.log('  info: ' + str(dict(st)))
        return st 

    def readdir(self, path, offset):
        self.log('readdir("%s")' % path)
        dir_ino = self.fs._inode_by_path(path)
        d = e2directory(self.fs, dir_ino)

        dirents = []
        for de in d.ent: dirents.append(de.name)
        
        self.log('  entries: %s' % str(dirents))
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

    def access(self, path, mode):
        self.log('access(%s, 0%o)' % (path, mode))
        try: ino = self._inode_by_path(path)
        except Exception:
            return False
        return True

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
    fsserv.parser.add_option(mountopt='user')
    fsserv.parse(values=fsserv, errex=1)
    fsserv.cwd = os.getcwd()

    # config
    fsserv.conf = dict()
    fsserv.conf['ro'] = True
    fsserv.conf['user'] = ('user' in fsserv.fuse_args.optlist)

    try: print fsserv.fuse_args.mount_expected()
    except OSError:
        print >> sys.stderr, "Mount expected failed"
        sys.exit(-1)
    fsserv.main()

if __name__ == '__main__':
    main(sys.argv)
