#!/usr/bin/python3

import threading
import logging
import time
from riscv import core, util, memory


def run_cpu(cpu: core.Core):

    logging.info('Starting thread %s', threading.current_thread().getName())
    logging.info(str(cpu))
    logging.info(str(cpu.inst_cache))

    direcciones = [4, 0, 8, 4, 12, 16, 32, 124]

    for addr in direcciones:
        w = cpu.inst_cache.load(addr)
        logging.debug('Got word {:d} @{:d}'.format(w, addr))
        cpu.clock_tick()

    logging.info('Simulando store en B0')
    cpu.inst_cache.sets[0].lines[0].flag = memory.FM
    cpu.inst_cache.sets[0].lines[0].data[0] = 200

    logging.info(str(cpu))
    logging.info(str(cpu.inst_cache))

    w = cpu.inst_cache.load(128)
    logging.debug('Got word {:d} @{:d}'.format(w, 128))
    cpu.clock_tick()


    logging.info('Thread ending %s', threading.current_thread().getName())
    logging.info(str(cpu))
    logging.info(str(cpu.inst_cache))

def main():
    log_format = "[%(threadName)s %(asctime)s,%(msecs)03d]: %(message)s"

    logging.basicConfig(format=log_format, level=logging.DEBUG, datefmt="%H:%M:%S")

    # TODO: create data structures
    global_vars = util.GlobalVars(1)

    core0 = core.Core('CPU0', global_vars)
    cache_ins0 = memory.CacheMemAssoc('$_Ins0', 0, 1024, 1, 8, 4, 4)

    core1 = core.Core('CPU1', global_vars)
    cache_ins1 = memory.CacheMemAssoc('$_Ins1', 0, 1024, 4, 8, 4, 4)

    core0.inst_cache = cache_ins0
    cache_ins0.owner_core = core0

    core1.inst_cache = cache_ins1
    cache_ins1.owner_core = core1

    mem_ins = memory.RamMemory('Memoria de instrucciones', start_addr=0, end_addr=1024, num_blocks=64, bpp=4, ppb=4)

    bus_ins = memory.Bus('Bus de instucciones', memory=mem_ins, caches=[cache_ins0, cache_ins1])

    # logging.info(str(cache_ins0))

    logging.info('Direcciones: [cpu0: {:s}, cpu1: {:s}, ins$0: {:s}, ins$1: {:s}, ins_mem: {:s}]'.format(hex(id(core0)), hex(id(core1)), hex(id(cache_ins0)), hex(id(cache_ins1)), hex(id(mem_ins))))
    logging.info(str(bus_ins))


    # Spawn child Threads
    t_cpu0 = threading.Thread(target=run_cpu, name='CPU0', args=(core0, ))
    #t_cpu1 = threading.Thread(target=run_cpu, name='CPU1', args=(core1, ))

    t_cpu0.start()
    #t_cpu1.start()

    logging.info('Thread {} spawned children'.format(threading.current_thread().getName()))
    time.sleep(1)

    t_cpu0.join()
    #t_cpu1.join()

    time.sleep(1)


if __name__ == '__main__':
    main()
