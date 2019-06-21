import threading
import logging
from typing import List, Optional
from .util import GlobalVars


PC_ADDRESS = 32
LR_ADDRESS = 33


class Register(object):
    address: int
    reg_type: str
    zero_reg: bool
    __data: int

    def __init__(self, address: int, reg_type: str, zero_reg: bool = False):
        self.address = address
        self.reg_type = reg_type
        self.zero_reg = zero_reg
        self.__data = 0

    @property
    def data(self):
        if self.zero_reg:
            return 0
        else:
            return self.__data

    @data.setter
    def data(self, var: int):
        """ Set the register's value
        :type var: int
        """
        if self.zero_reg:
            raise Exception('Trying to set Zero Register value')
        else:
            self.__data = var


class Pcb(object):
    registers: List[Register]
    pc: Register
    quantum: int

    def __init__(self):
        self.registers = [Register(i, 'General purpose', i == 0) for i in range(32)]
        self.pc = Register(PC_ADDRESS, 'PC')
        self.quantum = 0


class Core(object):
    r"""Clase que modela el núcleo"""
    __lr: Register
    __lr_lock: threading.RLock
    __pcb: Optional[Pcb]
    __global_vars: GlobalVars

    def __init__(self, name: str, global_vars: GlobalVars):

        self.name = name
        self.clock = 0

        self.__global_vars = global_vars
        self.__pcb = Pcb()

        self.__lr = Register(LR_ADDRESS, 'LR')
        self.__lr_lock = threading.RLock()

        self.data_cache = None
        self.inst_cache = None

    def fetch(self):
        pass

    def decode(self):
        pass

    def execute(self):
        pass

    def memory(self):
        pass

    def write_back(self):
        pass

    def step(self):

        self.fetch()
        self.decode()
        self.execute()
        self.memory()
        self.write_back()

        self.clock_tick()

        if self.__pcb.quantum > 0:
            self.__pcb.quantum -= 1


    def clock_tick(self):
        # logging.debug('Barrier id: {0:d}'.format(id(self.__global_vars.clock_barrier)))
        logging.debug('%s waiting for clock sync', self.name)
        self.__global_vars.clock_barrier.wait()
        self.clock += 1
        #time.sleep(1)

    def __str__(self):

        reg_str = '[\n '

        for i in range(len(self.__pcb.registers)):
            reg = self.__pcb.registers[i]
            reg_str += '[r{dir:02d}: {data:d}]'.format(dir=reg.address, data=reg.data)

            if i < len(self.__pcb.registers) - 1:
                reg_str += ','

            if (i+1)%8 == 0:
                reg_str +='\n '
            else:
                reg_str += ' '

        reg_str += ']'
        format_str = '{name:s}:\nPC: {pc:d}, LR: {lr:d}, ticks: {clock:d}\nRegs:\n{regs:s}\n'
        return format_str.format(name=self.name, pc=self.__pcb.pc.data, lr=self.__lr.data, clock=self.clock,
                                 regs=reg_str)

