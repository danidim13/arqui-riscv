from typing import List

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
