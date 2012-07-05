#!/usr/bin/env python

import os
import errno
import sys
import posix
import fuse

from ext2 import *

fuse.fuse_python_api = (0, 2)

logfile = '/tmp/e2fuse.log'

usage = '''
ext2 fuse filesystem
Usage:
$ e2fuse.py </image/file> </mount/dir>
''' + fuse.Fuse.fusage

class e2fuse(fuse.Fuse):
    def __init__(self, *args, **kw):
        fuse.Fuse.__init__(self, *args, **kw)
        self.logfile = open(logfile, 'w')
        self.log('Starting e2fuse...')

    def fsinit(self):
        if not hasattr(self, 'fs'):
            self._mount()

    def _mount(self):
        self.ro = self.conf['ro']
        imgf = self.cmdline[1][0]
        if imgf[0] is not '/': imgf = self.cwd + '/' + imgf
        try:
            self.fs = ext2fs(imgf)
            self.log('mounted successfully')
        except Exception as e:
            self.log('ext2fs(%s) failed: %s' % (imgf, e.message));

    def fsdestroy(self):
        self.log('fsdestoy()')
        self.fs.umount()

    def log(self, msg):
        self.logfile.write(msg + '\n')

    def getattr(self, path):
        self.log('getattr("%s")' % path)
        try: ent = self.fs._ent_by_path(path)
        except Ext2Exception:
            self.log('  no "%s"' % path)
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
        dir_dentry = self.fs._ent_by_path(path)
        d = self.fs._dir_by_inode(dir_dentry.inode)

        dirents = []
        for de in d.ent: dirents.append(de.name)

        self.log('  entries: %s' % str(dirents))
        for r in dirents:
            yield fuse.Direntry(r)

    def opendir(self, path):
        self.log('opendir(%s)' % path)
        return 0 #-errno.ENOSYS

    def releasedir(self, path):
        self.log('releasedir(%s)' % path)
        return 0 #-errno.ENOSYS

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
        try:
            buf = self.fs.read(path, offset, size)
            self.log('  %d bytes read' % len(buf))
            return buf
        except Ext2Exception as e:
            self.log('  Ext2Exception: %s' % e.message)
            return ''
        #except Exception as e:
        #    self.log('  Exception: %s' % e.message)
        #    return ''

    def write(self, path, buf, offset):
        self.log('write(%s, %d, %d)' % (path, len(buf), offset))
        if self.ro: return -errno.EROFS
        return -errno.ENOSYS

    def release(self, path, flags):
        return 0

    def open(self, path, flags):
        self.log('open(%s, 0x%x)' % (path, flags))
        return 0 #-errno.ENOSYS

    def create(self, path, mode, umask):
        self.log('create(%s, 0%o' % (path, mode))
        if self.ro: return -errno.EROFS
        return 0

    def access(self, path, mode):
        self.log('access(%s, 0%o)' % (path, mode))
        try:
            ino = self.fs._inode_by_path(path)
            #self.log('  - granted')
            return 0
        except Ext2Exception as e:
            self.log('  Ext2Exception: ' + e.message)
            return False
        except Exception as e:
            self.log('  Exception: ' + e.message)
            return False

    def truncate(self, path, size):
        self.log('truncate(%s, %d)' % (path, size))
        if self.ro: return -errno.EROFS
        return -errno.ENOSYS

    def ftruncate(self, fd, size):
        self.log('ftruncate(%d, %d)' % (fd, size))
        if self.ro: return -errno.EROFS
        return -errno.ENOSYS

    def utime(self, path, times):
        if self.ro: return -errno.EROFS
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

    def chown(self, path, uid, gid):
        self.log('chown(%s, %d:%d)' % (path, uid, gid))
        if self.ro: return -errno.EROFS
        return -errno.ENOSYS

    def chmod(self, path, mode):
        self.log('chmod(%s, 0%o)' % (path, mode))
        if self.ro: return -errno.EROFS
        return -errno.ENOSYS

    def fsync(self, path, isfsyncfile):
        self.log('fsync(%s)' % path)
        if self.ro: return -errno.EROFS
        return -errno.ENOSYS

    def flush(self, path):
        self.log('flush(%s)' % path)
        return 0

    def link(self, ):
        if self.ro: return -errno.EROFS
        return -errno.ENOSYS

    def symlink(self, target, name):
        if self.ro: return -errno.EROFS
        return -errno.ENOSYS

    def readlink(self, path):
        link = self.fs.readlink(path)
        self.log('readlink("%s") = %s' % (path, link))
        return link

    #def lock(self, l_type, l_whence, v2, name, l_start, l_len, l_pid):
    #    self.log('lock(%s, %d, %d, %d)' % (path, start, length, pid))
    #    return -errno.ENOSYS

    def bmap(self, path):
        self.log('bmap(%s)' % path)
        return -errno.ENOSYS

    def statvfs(self):
        self.log('statfs()')
        if not hasattr(self, 'fs'):
            self._mount()

        st = fuse.StatVfs()
        st.f_bsize = self.fs._blksz
        st.f_blocks = self.fs.sb.d['s_blocks_count']
        st.f_bfree = self.fs.sb.d['s_free_blocks_count']
        st.f_bavail = self.fs.sb.d['s_free_blocks_count'] - self.fs.sb.d['s_r_blocks_count']
        st.f_files = self.fs.sb.d['s_inodes_count']
        st.f_ffree = self.fs.sb.d['s_free_inodes_count']
        st.f_frsize = 0
        # if self.ro: st.f_flag = posix.ST_RDONLY
        st.f_namemax = 256

        return st

    def getxattr(self, path, name, param1):
        self.log('getxattr(%s, %s, %d)' % (path, name, param1))
        return -errno.ENOSYS

    def listxattr(self, path, attr):
        self.log('listxattr(%s)' % path)
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

    try:
        print fsserv.fuse_args.mount_expected()
    except OSError:
        print >> sys.stderr, "Mount expected failed"
        sys.exit(-1)
    fsserv.main()

if __name__ == '__main__':
    main(sys.argv)
