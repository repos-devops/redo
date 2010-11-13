#!/usr/bin/python
import sys, os, subprocess
import options
from helpers import *

optspec = """
redo [targets...]
--
d,debug    print dependency checks as they happen
v,verbose  print commands as they are run
ifchange   only redo if the file is modified or deleted
ifcreate   only redo if the file is created
"""
o = options.Options('redo', optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

targets = extra or ['it']


def relpath(t, base):
    t = os.path.abspath(t)
    tparts = t.split('/')
    bparts = base.split('/')
    for tp,bp in zip(tparts,bparts):
        if tp != bp:
            break
        tparts.pop(0)
        bparts.pop(0)
    while bparts:
        tparts.insert(0, '..')
        bparts.pop(0)
    return '/'.join(tparts)


def sname(typ, t):
    # FIXME: t.replace(...) is non-reversible and non-unique here!
    tnew = relpath(t, vars.BASE)
    #log('sname: (%r) %r -> %r\n' % (vars.BASE, t, tnew))
    return vars.BASE + ('/.redo/%s^%s' % (typ, tnew.replace('/', '^')))


def add_dep(t, mode, dep):
    open(sname('dep', t), 'a').write('%s %s\n' % (mode, dep))
    

def find_do_file(t):
    dofile = '%s.do' % t
    if os.path.exists(dofile):
        add_dep(t, 'm', dofile)
        if dirty_deps(dofile, depth = ''):
            build(dofile)
        return dofile
    else:
        add_dep(t, 'c', dofile)
        return None


def _dirty_deps(t, depth):
    debug('%s?%s\n' % (depth, t))
    if not os.path.exists(sname('stamp', t)):
        debug('%s-- DIRTY (no stamp)\n' % depth)
        return True

    stamptime = os.stat(sname('stamp', t)).st_mtime
    try:
        realtime = os.stat(t).st_mtime
    except OSError:
        realtime = 0

    if stamptime != realtime:
        debug('%s-- DIRTY (mtime)\n' % depth)
        return True
    
    for sub in open(sname('dep', t)).readlines():
        assert(sub[0] in ('c','m'))
        assert(sub[1] == ' ')
        assert(sub[-1] == '\n')
        mode = sub[0]
        name = sub[2:-1]
        if mode == 'c':
            if os.path.exists(name):
                debug('%s-- DIRTY (created)\n' % depth)
                return True
        elif mode == 'm':
            if dirty_deps(name, depth + '  '):
                #debug('%s-- DIRTY (sub)\n' % depth)
                return True
    return False


def dirty_deps(t, depth):
    if _dirty_deps(t, depth):
        unlink(sname('stamp', t))  # short circuit future checks
        return True
    return False


def stamp(t):
    stampfile = sname('stamp', t)
    if not os.path.exists(vars.BASE + '/.redo'):
        # .redo might not exist in a 'make clean' target
        return
    open(stampfile, 'w').close()
    try:
        mtime = os.stat(t).st_mtime
    except OSError:
        mtime = 0
    os.utime(stampfile, (mtime, mtime))


def _preexec(t):
    os.environ['REDO_TARGET'] = t
    os.environ['REDO_DEPTH'] = vars.DEPTH + '  '
    dn = os.path.dirname(t)
    if dn:
        os.chdir(dn)


def build(t):
    unlink(sname('dep', t))
    open(sname('dep', t), 'w').close()
    dofile = find_do_file(t)
    if not dofile:
        if os.path.exists(t):  # an existing source file
            stamp(t)
            return  # success
        else:
            raise Exception('no rule to make %r' % t)
    unlink(t)
    tmpname = '%s.redo.tmp' % t
    unlink(tmpname)
    f = open(tmpname, 'w+')
    argv = ['sh', '-e', os.path.basename(dofile),
            os.path.basename(t), 'FIXME', os.path.basename(tmpname)]
    if vars.VERBOSE:
        argv[1] += 'v'
    log('%s\n' % t)
    rv = subprocess.call(argv, preexec_fn=lambda: _preexec(t),
                         stdout=f.fileno())
    st = os.stat(tmpname)
    #log('rv: %d (%d bytes) (%r)\n' % (rv, st.st_size, dofile))
    stampfile = sname('stamp', t)
    if rv==0:
        if st.st_size:
            os.rename(tmpname, t)
        else:
            unlink(tmpname)
        stamp(t)
    else:
        unlink(tmpname)
        unlink(stampfile)
    f.close()
    if rv != 0:
        raise Exception('non-zero return code building %r' % t)


if opt.debug:
    os.environ['REDO_DEBUG'] = '1'
if opt.verbose:
    os.environ['REDO_VERBOSE'] = '1'
assert(not (opt.ifchange and opt.ifcreate))

if not os.environ.get('REDO_BASE', ''):
    base = os.path.commonprefix([os.path.abspath(os.path.dirname(t))
                                 for t in targets] + [os.getcwd()])
    bsplit = base.split('/')
    for i in range(len(bsplit)-1, 0, -1):
        newbase = '%s/.redo' % '/'.join(bsplit[:i])
        if os.path.exists(newbase):
            base = newbase
            break
    os.environ['REDO_BASE'] = base

import vars
from log import *

if not vars.DEPTH:
    # toplevel call to redo
    exenames = [os.path.abspath(sys.argv[0]), os.path.realpath(sys.argv[0])]
    if exenames[0] == exenames[1]:
        exenames = [exenames[0]]
    dirnames = [os.path.dirname(p) for p in exenames]
    os.environ['PATH'] = ':'.join(dirnames) + ':' + os.environ['PATH']

startdir = os.getcwd()
for t in targets:
    mkdirp('%s/.redo' % vars.BASE)
    os.chdir(startdir)
    
    if vars.TARGET:
        add_dep(vars.TARGET, opt.ifcreate and 'c' or 'm', t)
    if opt.ifcreate:
        pass # just adding the dependency (above) is enough
    elif opt.ifchange:
        if dirty_deps(t, depth = ''):
            build(t)
    else:
        build(t)
