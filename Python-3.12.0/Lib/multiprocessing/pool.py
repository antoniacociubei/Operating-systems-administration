#
# Module providing the `Pool` class for managing a process pool
#
# multiprocessing/pool.py
#
# Copyright (c) 2006-2008, R Oudkerk
# Licensed to PSF under a Contributor Agreement.
#

__all__ = ['Pool', 'ThreadPool']

#
# Imports
#

import collections
import itertools
import os
import queue
import threading
import time
import traceback
import types
import warnings

# If threading is available then ThreadPool should be provided.  Therefore
# we avoid top-level imports which are liable to fail on some systems.
from . import util
from . import get_context, TimeoutError
from .connection import wait

#
# Constants representing the state of a pool
#

INIT = "INIT"
RUN = "RUN"
CLOSE = "CLOSE"
TERMINATE = "TERMINATE"

#
# Miscellaneous
#

job_counter = itertools.count()

def mapstar(args):
    return list(map(*args))

def starmapstar(args):
    return list(itertools.starmap(args[0], args[1]))

#
# Hack to embed stringification of remote traceback in local traceback
#

class RemoteTraceback(Exception):
    def __init__(self, tb):
        self.tb = tb
    def __str__(self):
        return self.tb

class ExceptionWithTraceback:
    def __init__(self, exc, tb):
        tb = traceback.format_exception(type(exc), exc, tb)
        tb = ''.join(tb)
        self.exc = exc
        self.tb = '\n"""\n%s"""' % tb
    def __reduce__(self):
        return rebuild_exc, (self.exc, self.tb)

def rebuild_exc(exc, tb):
    exc.__cause__ = RemoteTraceback(tb)
    return exc

#
# Code run by worker processes
#

class MaybeEncodingError(Exception):
    """Wraps possible unpickleable errors, so they can be
    safely sent through the socket."""

    def __init__(self, exc, value):
        self.exc = repr(exc)
        self.value = repr(value)
        super(MaybeEncodingError, self).__init__(self.exc, self.value)

    def __str__(self):
        return "Error sending result: '%s'. Reason: '%s'" % (self.value,
                                                             self.exc)

    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self)


def worker(inqueue, outqueue, initializer=None, initargs=(), maxtasks=None,
           wrap_exception=False):
    if (maxtasks is not None) and not (isinstance(maxtasks, int)
                                       and maxtasks >= 1):
        raise AssertionError("Maxtasks {!r} is not valid".format(maxtasks))
    put = outqueue.put
    get = inqueue.get
    if hasattr(inqueue, '_writer'):
        inqueue._writer.close()
        outqueue._reader.close()

    if initializer is not None:
        initializer(*initargs)

    completed = 0
    while maxtasks is None or (maxtasks and completed < maxtasks):
        try:
            task = get()
        except (EOFError, OSError):
            util.debug('worker got EOFError or OSError -- exiting')
            break

        if task is None:
            util.debug('worker got sentinel -- exiting')
            break

        job, i, func, args, kwds = task
        try:
            result = (True, func(*args, **kwds))
        except Exception as e:
            if wrap_exception and func is not _helper_reraises_exception:
                e = ExceptionWithTraceback(e, e.__traceback__)
            result = (False, e)
        try:
            put((job, i, result))
        except Exception as e:
            wrapped = MaybeEncodingError(e, result[1])
            util.debug("Possible encoding error while sending result: %s" % (
                wrapped))
            put((job, i, (False, wrapped)))

        task = job = result = func = args = kwds = None
        completed += 1
    util.debug('worker exiting after %d tasks' % completed)

def _helper_reraises_exception(ex):
    'Pickle-able helper function for use by _guarded_task_generation.'
    raise ex

#
# Class representing a process pool
#

class _PoolCache(dict):
    """
    Class that implements a cache for the Pool class that will notify
    the pool management threads every time the cache is emptied. The
    notification is done by the use of a queue that is provided when
    instantiating the cache.
    """
    def __init__(self, /, *args, notifier=None, **kwds):
        self.notifier = notifier
        super().__init__(*args, **kwds)

    def __delitem__(self, item):
        super().__delitem__(item)

        # Notify that the cache is empty. This is important because the
        # pool keeps maintaining workers until the cache gets drained. This
        # eliminates a race condition in which a task is finished after the
        # the pool's _handle_workers method has enter another iteration of the
        # loop. In this situation, the only event that can wake up the pool
        # is the cache to be emptied (no more tasks available).
        if not self:
            self.notifier.put(None)

class Pool(object):
    '''
    Class which supports an async version of applying functions to arguments.
    '''
    _wrap_exception = True

    @staticmethod
    def Process(ctx, *args, **kwds):
        return ctx.Process(*args, **kwds)

    def __init__(self, processes=None, initializer=None, initargs=(),
                 maxtasksperchild=None, context=None):
        # Attributes initialized early to make sure that they exist in
        # __del__() if __init__() raises an exception
        self._pool = []
        self._state = INIT

        self._ctx = context or get_context()
        self._setup_queues()
        self._taskqueue = queue.SimpleQueue()
        # The _change_notifier queue exist to wake up self._handle_workers()
        # when the cache (self._cache) is empty or when there is a change in
        # the _state variable of the thread that runs _handle_workers.
        self._change_notifier = self._ctx.SimpleQueue()
        self._cache = _PoolCache(notifier=self._change_notifier)
        self._maxtasksperchild = maxtasksperchild
        self._initializer = initializer
        self._initargs = initargs

        if processes is None:
            processes = os.cpu_count() or 1
        if processes < 1:
            raise ValueError("Number of processes must be at least 1")
        if maxtasksperchild is not None:
            if not isinstance(maxtasksperchild, int) or maxtasksperchild <= 0:
                raise ValueError("maxtasksperchild must be a positive int or None")

        if initializer is not None and not callable(initializer):
            raise TypeError('initializer must be a callable')

        self._processes = processes
        try:
            self._repopulate_pool()
        except Exception:
            for p in self._pool:
                if p.exitcode is None:
                    p.terminate()
            for p in self._pool:
                p.join()
            raise

        sentinels = self._get_sentinels()

        self._worker_handler = threading.Thread(
            target=Pool._handle_workers,
            args=(self._cache, self._taskqueue, self._ctx, self.Process,
                  self._processes, self._pool, self._inqueue, self._outqueue,
                  self._initializer, self._initargs, self._maxtasksperchild,
                  self._wrap_exception, sentinels, self._change_notifier)
            )
        self._worker_handler.daemon = True
        self._worker_handler._state = RUN
        self._worker_handler.start()


        self._task_handler = threading.Thread(
            target=Pool._handle_tasks,
            args=(self._taskqueue, self._quick_put, self._outqueue,
                  self._pool, self._cache)
            )
        self._task_handler.daemon = True
        self._task_handler._state = RUN
        self._task_handler.start()

        self._result_handler = threading.Thread(
            target=Pool._handle_results,
            args=(self._outqueue, self._quick_get, self._cache)
            )
        self._result_handler.daemon = True
        self._result_handler._state = RUN
        self._result_handler.start()

        self._terminate = util.Finalize(
            self, self._terminate_pool,
            args=(self._taskqueue, self._inqueue, self._outqueue, self._pool,
                  self._change_notifier, self._worker_handler, self._task_handler,
                  self._result_handler, self._cache),
            exitpriority=15
            )
        self._state = RUN

    # Copy globals as function locals to make sure that they are available
    # during Python shutdown when the Pool is destroyed.
    def __del__(self, _warn=warnings.warn, RUN=RUN):
        if self._state == RUN:
            _warn(f"unclosed running multiprocessing pool {self!r}",
                  ResourceWarning, source=self)
            if getattr(self, '_change_notifier', None) is not None:
                self._change_notifier.put(None)

    def __repr__(self):
        cls = self.__class__
        return (f'<{cls.__module__}.{cls.__qualname__} '
                f'state={self._state} '
                f'pool_size={len(self._pool)}>')

    def _get_sentinels(self):
        task_queue_sentinels = [self._outqueue._reader]
        self_notifier_sentinels = [self._change_notifier._reader]
        return [*task_queue_sentinels, *self_notifier_sentinels]

    @staticmethod
    def _get_worker_sentinels(workers):
        return [worker.sentinel for worker in
                workers if hasattr(worker, "sentinel")]

    @staticmethod
    def _join_exited_workers(pool):
        """Cleanup after any worker processes which have exited due to reaching
        their specified lifetime.  Returns True if any workers were cleaned up.
        """
        cleaned = False
        for i in reversed(range(len(pool))):
            worker = pool[i]
            if worker.exitcode is not None:
                # worker exited
            