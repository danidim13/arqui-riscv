#!/usr/bin/python3

import threading
import logging
import time
from riscv import core, util, memory, hilo


def run_cpu(cpu: core.Core):
    logging.info('Iniciando ejecución de {:s}'.format(cpu.name))
    cpu.run()

    logging.info('Iddling Core {:s}'.format(cpu.name))

    while not cpu._global_vars.done:
        cpu.iddle()

    logging.info('Finalizando ejecución de {:s}'.format(cpu.name))


def setup_modules(global_vars):
    mem_data = memory.RamMemory('Memoria de datos', start_addr=0, end_addr=384, num_blocks=24, bpp=4, ppb=4)
    mem_inst = memory.RamMemory('Memoria de instrucciones', start_addr=384, end_addr=1024, num_blocks=40, bpp=4, ppb=4)
    core0 = core.Core('CPU0', global_vars)
    cache_inst0 = memory.CacheMemAssoc('Inst$0', start_addr=384, end_addr=1024, assoc=1, num_blocks=8, bpp=4, ppb=4)
    cache_data0 = memory.CacheMemAssoc('Data$0', start_addr=0, end_addr=384, assoc=4, num_blocks=8, bpp=4, ppb=4)
    core1 = core.Core('CPU1', global_vars)
    cache_inst1 = memory.CacheMemAssoc('Inst$1', start_addr=384, end_addr=1024, assoc=1, num_blocks=8, bpp=4, ppb=4)
    cache_data1 = memory.CacheMemAssoc('Data$1', start_addr=0, end_addr=384, assoc=1, num_blocks=8, bpp=4, ppb=4)

    core0.inst_cache = cache_inst0
    core0.data_cache = cache_data0
    cache_inst0.owner_core = core0
    cache_data0.owner_core = core0

    core1.inst_cache = cache_inst1
    core1.data_cache = cache_data1
    cache_inst1.owner_core = core1
    cache_data1.owner_core = core1

    bus_inst = memory.Bus('Bus de instucciones', memory=mem_inst, caches=[cache_inst0, cache_inst1])
    bus_data = memory.Bus('Bus de datos', memory=mem_data, caches=[cache_data0, cache_data1])

    return core0, cache_inst0, cache_data0, core1, cache_inst1, cache_data1, mem_inst, bus_inst, mem_data, bus_data


def prueba_hilo20():

    log_format = "[%(threadName)s %(asctime)s,%(msecs)03d]: %(message)s"
    logging.basicConfig(format=log_format, level=logging.INFO, datefmt="%H:%M:%S")

    global_vars = util.GlobalVars(1)
    core0, cache_inst0, cache_data0, core1, cache_inst1, cache_data1, mem_inst, bus_inst, mem_data, bus_data = setup_modules(global_vars)

    datos = hilo.read_hilo('../hilos/20.txt')

    mem_inst.load(384, datos)
    core0.pc.data = 384
    logging.info(str(mem_inst))

    logging.info('Iniciando simulación single Core')
    logging.info(str(core0))

    for i in range(17):
        core0.step()

    logging.info('Fin simulación single Core')
    logging.info(str(core0))


def prueba_hilo12():

    log_format = "[%(threadName)s %(asctime)s,%(msecs)03d]: %(message)s"
    logging.basicConfig(format=log_format, level=logging.INFO, datefmt="%H:%M:%S")

    global_vars = util.GlobalVars(1)
    core0, cache_inst0, cache_data0, core1, cache_inst1, cache_data1, mem_inst, bus_inst, mem_data, bus_data = setup_modules(global_vars)

    datos = hilo.read_hilo('../hilos/13.txt')

    mem_inst.load(384, datos)
    core0.pc.data = 384
    logging.info(str(mem_inst))

    logging.info('Iniciando simulación single Core')
    logging.info(str(core0))

    while core0.state == core.Core.RUN:
        core0.step()

    logging.info('Fin simulación single Core')
    logging.info(str(core0))
    logging.info(str(cache_data0))
    logging.info(str(mem_data))

def prueba_varios_hilos():

    log_format = "[%(threadName)s %(asctime)s,%(msecs)03d]: %(message)s"
    logging.basicConfig(format=log_format, level=logging.DEBUG, datefmt="%H:%M:%S")

    programs = ['./hilos/11.txt',
                './hilos/12.txt',
                './hilos/13.txt',
                './hilos/14.txt',
                './hilos/15.txt',
                './hilos/16.txt']

    global_vars = util.GlobalVars(1)
    core0, cache_inst0, cache_data0, core1, cache_inst1, cache_data1, mem_inst, bus_inst, mem_data, bus_data = setup_modules(global_vars)
    mem_inst.data_format = 'default'

    inst_addr = 384
    util.cargar_hilos(programs, global_vars.scheduler, mem_inst, inst_addr)
    logging.info(mem_inst)

    core0.run()

    logging.info('Finalizando simulación a continuación se presenta el estado final\n\n\n')

    for i in range(len(programs)):
        pcb = global_vars.scheduler.finished_queue.get_nowait()
        logging.info(pcb)

    logging.info(core0)
    logging.info(cache_data0)
    logging.info(mem_data)


def prueba_multicore_lrsc():

    log_format = "[%(threadName)s %(asctime)s,%(msecs)03d]: %(message)s"
    logging.basicConfig(format=log_format, level=logging.INFO, datefmt="%H:%M:%S")

    programs = ['./hilos_adv/0.txt',
                './hilos_adv/1.txt',
                './hilos_adv/2.txt',
                './hilos_adv/3.txt',
                './hilos_adv/4.txt',
                './hilos_adv/5.txt',
                './hilos_adv/6.txt']

    global_vars = util.GlobalVars(3)
    core0, cache_inst0, cache_data0, core1, cache_inst1, cache_data1, mem_inst, bus_inst, mem_data, bus_data = setup_modules(global_vars)
    mem_inst.data_format = 'default'

    inst_addr = 384
    util.cargar_hilos(programs, global_vars.scheduler, mem_inst, inst_addr)
    logging.info(mem_inst)

    t_cpu0 = threading.Thread(target=run_cpu, name='CPU0', args=(core0, ))
    t_cpu1 = threading.Thread(target=run_cpu, name='CPU1', args=(core1, ))

    t_cpu0.start()
    t_cpu1.start()

    logging.info('Thread {} spawned children'.format(threading.current_thread().getName()))

    while not global_vars.done:
        while global_vars.clock_barrier.n_waiting < 2:
            time.sleep(0.001)

        # logging.debug("Ambos hilos llegaron a clock")

        for c in [core0, core1]:
            if c.state == core.Core.IDL:
                logging.debug('{:s} ya terminó'.format(c.name))

        if core0.state == core.Core.IDL and core1.state == core.Core.IDL:
            logging.info('Ambos Cores terminaron, finalizando simulación')
            global_vars.done = True

        global_vars.clock_barrier.wait()

    t_cpu0.join()
    t_cpu1.join()

    logging.info('Finalizando simulación a continuación se presenta el estado final\n\n\n')

    for i in range(len(programs)):
        pcb = global_vars.scheduler.finished_queue.get_nowait()
        logging.info(pcb)

    logging.info(core0)
    logging.info(cache_data0)
    logging.info(core1)
    logging.info(cache_data1)
    logging.info(mem_data)



def prueba_multicore():

    log_format = "[%(threadName)s %(asctime)s,%(msecs)03d]: %(message)s"
    logging.basicConfig(format=log_format, level=logging.DEBUG, datefmt="%H:%M:%S")

    programs = ['./hilos/11.txt',
                './hilos/12.txt',
                './hilos/13.txt',
                './hilos/14.txt',
                './hilos/15.txt',
                './hilos/16.txt']

    global_vars = util.GlobalVars(3)
    core0, cache_inst0, cache_data0, core1, cache_inst1, cache_data1, mem_inst, bus_inst, mem_data, bus_data = setup_modules(global_vars)
    mem_inst.data_format = 'default'

    inst_addr = 384
    util.cargar_hilos(programs, global_vars.scheduler, mem_inst, inst_addr)
    logging.info(mem_inst)


    t_cpu0 = threading.Thread(target=run_cpu, name='CPU0', args=(core0, ))
    t_cpu1 = threading.Thread(target=run_cpu, name='CPU1', args=(core1, ))

    t_cpu0.start()
    t_cpu1.start()

    logging.info('Thread {} spawned children'.format(threading.current_thread().getName()))

    while not global_vars.done:
        while global_vars.clock_barrier.n_waiting < 2:
            time.sleep(0.001)

        # logging.debug("Ambos hilos llegaron a clock")

        for c in [core0, core1]:
            if c.state == core.Core.IDL:
                logging.debug('{:s} ya terminó'.format(c.name))

        if core0.state == core.Core.IDL and core1.state == core.Core.IDL:
            logging.info('Ambos Cores terminaron, finalizando simulación')
            global_vars.done = True

        global_vars.clock_barrier.wait()

    t_cpu0.join()
    t_cpu1.join()

    logging.info('Finalizando simulación a continuación se presenta el estado final\n\n\n')

    for i in range(len(programs)):
        pcb = global_vars.scheduler.finished_queue.get_nowait()
        logging.info(pcb)

    logging.info(core0)
    logging.info(cache_data0)
    logging.info(core1)
    logging.info(cache_data1)
    logging.info(mem_data)



def main():

    log_format = "[%(threadName)s %(asctime)s,%(msecs)03d]: %(message)s"
    logging.basicConfig(format=log_format, level=logging.DEBUG, datefmt="%H:%M:%S")

    # TODO: create data structures
    global_vars = util.GlobalVars(1)

    core0, cache_inst0, cache_data0, core1, cache_inst1, cache_data1, mem_inst, bus_inst, mem_data, bus_data = setup_modules(global_vars)

    # logging.info(str(cache_ins0))

    logging.info('Direcciones: [cpu0: {:s}, cpu1: {:s}, inst$0: {:s}, inst$1: {:s}, ins_mem: {:s}]'.format(hex(id(core0)), hex(id(core1)), hex(id(cache_inst0)), hex(id(cache_inst1)), hex(id(mem_inst))))
    logging.info(str(bus_inst))


    # Spawn child Threads
    t_cpu0 = threading.Thread(target=run_cpu, name='CPU0', args=(core0, core1))
    #t_cpu1 = threading.Thread(target=run_cpu, name='CPU1', args=(core1, ))

    t_cpu0.start()
    #t_cpu1.start()

    logging.info('Thread {} spawned children'.format(threading.current_thread().getName()))
    time.sleep(1)

    t_cpu0.join()
    #t_cpu1.join()

    time.sleep(1)
    logging.info(str(mem_inst))


if __name__ == '__main__':
    prueba_multicore_lrsc()
