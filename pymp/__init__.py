"""Main package."""
# pylint: disable=invalid-name
from __future__ import print_function

import os as _os
import sys as _sys
import logging as _logging
import multiprocessing as _multiprocessing

import pymp.shared as _shared
import pymp.config as _config

_LOGGER = _logging.getLogger(__name__)

# pylint: disable=too-few-public-methods
class Parallel(object):

    """A parallel region."""

    _level = 0

    def __init__(self,
                 num_threads=None):  # pylint: disable=redefined-outer-name
        self._num_threads = num_threads
        self._is_fork = False
        self._pids = []
        self._thread_num = 0

    def __enter__(self):
        # pylint: disable=global-statement
        assert len(self._pids) == 0, (
            "A `Parallel` object may only be used once!"
        )
        # pylint: disable=protected-access
        if self._num_threads is None:
            assert (len(_config.num_threads) == 1 or
                    len(_config.num_threads) > Parallel._level), (
                        "The value of PYMP_NUM_THREADS/OMP_NUM_THREADS must be "
                        "either a single positive number or a comma-separated "
                        "list of number per nesting level.")
            if len(_config.num_threads) == 1:
                self._num_threads = _config.num_threads[0]
            else:
                self._num_threads = _config.num_threads[Parallel._level]
        if not _config.nested:
            assert Parallel._level == 0, (
                "No nested parallel contexts allowed!")
        _LOGGER.debug("Entering `Parallel` context (level %d). Forking...",
                      Parallel._level)
        Parallel._level += 1
        # pylint: disable=protected-access
        with _shared._NUM_PROCS.get_lock():
            # Make sure, max threads is not exceeded.
            if _config.thread_limit is not None:
                # pylint: disable=protected-access
                num_active = _shared._NUM_PROCS.value
                self._num_threads = min(self._num_threads,
                                        _config.thread_limit - num_active + 1)
            _shared._NUM_PROCS.value += self._num_threads - 1
        for thread_num in range(1, self._num_threads):
            pid = _os.fork()
            if pid == 0:
                # Forked process.
                self._is_fork = True
                self._thread_num = thread_num
                break
            else:
                # pylint: disable=protected-access
                self._pids.append(pid)
        if not self._is_fork:
            _LOGGER.debug("Forked to processes: %s.",
                          str(self._pids))
        return self

    def __exit__(self, exc_t, exc_val, exc_tb):
        if self._is_fork:
            _os._exit(1)  # pylint: disable=protected-access
        else:
            for pid in self._pids:
                _LOGGER.debug("Waiting for process %d...",
                              pid)
                _os.waitpid(pid, 0)
            # pylint: disable=protected-access
            with _shared._NUM_PROCS.get_lock():
                _shared._NUM_PROCS.value -= len(self._pids)
        Parallel._level -= 1
        _LOGGER.debug("Parallel region left.")

    @property
    def thread_num(self):
        """The worker index."""
        return self._thread_num

    def range(self, start, stop=None, step=1):
        """
        Get the correctly distributed parallel chunks.

        Currently only support 'static' schedule.
        """
        if stop is None:
            start, stop = 0, start
        full_list = range(start, stop, step)
        per_worker = len(full_list) // self._num_threads
        rem = len(full_list) % self._num_threads
        schedule = [per_worker + 1
                    if thread_idx < rem else per_worker
                    for thread_idx in range(self._num_threads)]
        # pylint: disable=undefined-variable
        start_idx = reduce(lambda x, y: x+y, schedule[:self.thread_num], 0)
        end_idx = start_idx + schedule[self._thread_num]
        return full_list[start_idx:end_idx]
