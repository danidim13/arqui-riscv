import threading
import logging

from typing import List

from .hilo import Scheduler, Pcb
from .isa import encode, decode
from .memory import RamMemory


class GlobalVars(object):

    def __init__(self, num_cpus: int):
        self.clock_barrier = threading.Barrier(parties=num_cpus)
        self.scheduler = Scheduler()

        self.done = False


def cargar_hilos(files: List[str], scheduler: Scheduler, inst_mem: RamMemory, start_addr: int):

    programs_loaded = 0
    addr = start_addr

    for filename in files:

        print('Cargando {:s} en memoria de datos, pid {:d}'.format(filename, programs_loaded))
        programa = read_hilo(filename)
        inst_mem.load(addr, programa)
        pcb = Pcb(programs_loaded, addr, filename)
        scheduler.put_ready(pcb)

        programs_loaded += 1
        addr += len(programa)*4

    return programs_loaded


def read_hilo(filename: str):

    instructions = []
    with open(filename, 'r') as file:

        for line in file:
            ins = [int(num) for num in line.split()]
            assert len(ins) == 4

            opcode, arg1, arg2, arg3 = ins
            encoded_ins = encode(opcode, arg1, arg2, arg3)
            assert ins == [v for v in decode(encoded_ins)]

            logging.debug('Instrucción: {:<20s} codificada: 0x{:08X}'.format(str(ins), encoded_ins))

            instructions.append(encoded_ins)

    return instructions


