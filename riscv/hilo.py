from queue import Queue

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

    READY = 0
    RUNNING = 1
    FINISHED = 2

    def __init__(self, pid: int = 0, starting_addr: int = 384, name: str = 'default'):
        assert pid >= 0
        assert 384 <= starting_addr < 1024
        self.pid = pid
        self.name = name
        self.registers = [0 for i in range(32)]
        self.pc = starting_addr
        self.quantum = 0
        self.hits = 0
        self.misses = 0
        self.ticks = 0
        self.status = self.READY

    def __str__(self):
        if self.status == self.READY:
            estado = 'READY'
        elif self.status == self.RUNNING:
            estado = 'RUNNING'
        else:
            estado = 'FINISHED'

        reg_str = '[\n '

        reg_data_len = max([len(str(data)) for data in self.registers])

        for i in range(len(self.registers)):
            data = self.registers[i]
            reg_str += '[r{dir:02d}: {data:{reg_len}d}]'.format(dir=i, data=data, reg_len=reg_data_len)

            if i < len(self.registers) - 1:
                reg_str += ','

                if (i+1)%8 == 0:
                    reg_str +='\n '
                else:
                    reg_str += ' '

        reg_str += '\n]'

        format_str = 'P{:02d}: hilo "{:s}" con estado {:s}\nPc: {:d}, ciclos: {:d}, hits: {:d}, misses: {:d}\nRegs:\n{:s}\n'
        return format_str.format(self.pid, self.name, estado, self.pc, self.ticks, self.hits, self.misses, reg_str)


class Scheduler(object):

    INIT_QUANTUM = 25

    def __init__(self):
        self.ready_queue = Queue()
        self.finished_queue = Queue()

    def next_ready_thread(self) -> Pcb:
        return self.ready_queue.get(block=False)

    def put_ready(self, item: Pcb):
        assert item.quantum == 0
        item.quantum = self.INIT_QUANTUM
        return self.ready_queue.put(item, block=False)

    def put_finished(self, item: Pcb):
        assert item.quantum == 0
        return self.finished_queue.put(item, block=False)
