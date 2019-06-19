#!/usr/bin/python3

import threading
import logging
import time
from riscv import core, util


def run_cpu(cpu: core.Core):

    logging.info('Starting thread %s', threading.current_thread().getName())
    logging.info(str(cpu))

    for i in range(5):
        cpu.step()

    logging.info('Thread ending %s', threading.current_thread().getName())


def main():
    format = "[%(threadName)s %(asctime)s,%(msecs)d]: %(message)s"

    logging.basicConfig(format=format, level=logging.DEBUG, datefmt="%H:%M:%S")

    # TODO: create data structures
    global_vars = util.GlobalVars(2)
    core0 = core.Core('CPU0', global_vars)
    core1 = core.Core('CPU1', global_vars)

    # Spawn child Threads
    t_cpu0 = threading.Thread(target=run_cpu, name='CPU0', args=(core0, ))
    t_cpu1 = threading.Thread(target=run_cpu, name='CPU1', args=(core1, ))

    t_cpu0.start()
    t_cpu1.start()

    logging.info('Thread {} spawned children'.format(threading.current_thread().getName()))

    t_cpu0.join()
    t_cpu1.join()
    time.sleep(1)


if __name__ == '__main__':
    main()
