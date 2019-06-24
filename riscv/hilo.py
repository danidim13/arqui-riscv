from typing import List
from .isa import encode, decode
import logging

class Pcb(object):
    pid: int
    name: str
    registers: List[int]
    pc: int
    quantum: int
    hits: int
    misses: int
    ticks: int
    status: str

    def __init__(self, pid: int = 0, name: str = 'default'):
        self.pid = pid
        self.name = name
        self.registers = [0 for i in range(32)]
        self.pc = 0
        self.quantum = 0
        self.hits = 0
        self.misses = 0
        self.ticks = 0
        self.status = 0

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

