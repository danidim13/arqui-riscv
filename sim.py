#! /usr/bin/env python3
# -*- coding: utf8 -*-

import argparse
import textwrap
import logging
import os
import time
import threading
from riscv import core, util, memory, hilo
from typing import List


def main():
    parser = make_parser()
    args = parser.parse_args()

    log_format = "[%(threadName)s %(asctime)s,%(msecs)03d]: %(message)s"

    if args.verbose == 0:
        level = logging.WARNING
    elif args.verbose == 1:
        level = logging.INFO
    elif args.verbose > 1:
        level = logging.DEBUG

    logging.basicConfig(format=log_format, level=level, datefmt="%H:%M:%S")

    print(str(args))

    if args.dir is not None:
        if not os.path.isdir(args.dir):
            parser.error('{:s} no es una carpeta'.format(args.dir))

        programas = [os.path.join(args.dir, p) for p in os.listdir(args.dir) if os.path.isfile(os.path.join(args.dir, p))]

    elif args.files is not None:
        programas = args.files

    else:
        parser.error('Error, no proporcionó hilillos')

    return run_tmain(programas)


def make_parser():
    description_es = textwrap.dedent('''\
        Simulador de RISC-V multinucleo.
        Ejecuta los hilillos contenidos en cada ARCHIVO o en la CARPETA
        
        Al final de la ejecución imprime los contenidos de la memoria y los
        cachés de datos, así como el estado final de los procesadores,
        hilillos y estadísticas de ejecución
        
        ''')

    epilog_es = textwrap.dedent('''\
        ECCI-UCR
        CI-1323 Arquitectura de computadoras
        Desarrollado por Daniel Díaz © 2019
        ''')

    file_meta_es = 'ARCHIVO'
    file_help_es = 'ruta del archivo o archivos con los hilillo que quiere ejecutar'

    dir_meta_es = 'CARPETA'
    dir_help_es = 'ruta de la carpeta con hilillos que quiere ejecutar'

    verbosity_help_es = 'aumenta el nivel de verbosidad, se puede incluir hasta 2 veces para imprimir más información' \
                        ' de la ejecución en pantalla (-v ó -vv)'

    parser = argparse.ArgumentParser(description=description_es, epilog=epilog_es,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument('--verbose', '-v', action='count', help=verbosity_help_es, default=0)

    meg = parser.add_mutually_exclusive_group(required=True)
    meg.add_argument('-f', '--files', type=str, metavar=file_meta_es, nargs='+', help=file_help_es)
    meg.add_argument('-d', '--dir', type=str, metavar=dir_meta_es, help=dir_help_es)

    return parser


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


def run_tcpu(cpu):
    print('Iniciando ejecución de {:s}'.format(cpu.name))
    logging.info('Running Core {:s}'.format(cpu.name))
    cpu.run()

    logging.info('Iddling Core {:s}'.format(cpu.name))

    while not cpu._global_vars.done:
        cpu.iddle()

    logging.info('Finalizing Core {:s}'.format(cpu.name))
    print('Finalizando ejecución de {:s}'.format(cpu.name))
    return


def run_tmain(programs: List[str]):

    global_vars = util.GlobalVars(3)
    core0, cache_inst0, cache_data0, core1, cache_inst1, cache_data1, mem_inst, bus_inst, mem_data, bus_data = setup_modules(global_vars)
    mem_inst.data_format = 'default'

    inst_addr = 384
    util.cargar_hilos(programs, global_vars.scheduler, mem_inst, inst_addr)
    logging.info(mem_inst)

    t_cpu0 = threading.Thread(target=run_tcpu, name='CPU0', args=(core0, ))
    t_cpu1 = threading.Thread(target=run_tcpu, name='CPU1', args=(core1, ))

    print('Iniciando simulación')

    t_cpu0.start()
    t_cpu1.start()

    logging.info('Thread {} spawned children'.format(threading.current_thread().getName()))

    iter = 0

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

        iter += 1
        if (iter % 200) == 0:
            print('.', end='', flush=True)

        global_vars.clock_barrier.wait()

    print('')

    t_cpu0.join()
    t_cpu1.join()

    print('\nFinalizando simulación a continuación se presenta el estado final\n\n')

    hilillos = []
    for i in range(len(programs)):
        hilillos.append(global_vars.scheduler.finished_queue.get_nowait())

    print('--------------- Hilillos ---------------\n')

    print('PID | <archivo>')
    print('----+----------')
    for pcb in hilillos:
        print('{: 3d} | {:s}'.format(pcb.pid, pcb.name))

    print('')
    for pcb in hilillos:
        print(pcb)

    print('\n--------------- Core 0 ---------------\n')
    print(core0)
    print('\n--------------- Caché 0 ---------------\n')
    print(cache_data0)
    print('\n--------------- Core 1 ---------------\n')
    print(core1)
    print('\n--------------- Caché 1 ---------------\n')
    print(cache_data1)
    print('\n--------------- Memoria de datos ---------------\n')
    print(mem_data)


if __name__ == '__main__':
    main()
