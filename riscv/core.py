import threading
from typing import List, Optional


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
    __lr_lock: threading.Lock
    __pcb: Optional[Pcb]

    def __init__(self, name: str, global_vars):

        self.name = name
        self.clock = 0

        self.__global_vars = global_vars
        self.__pcb = Pcb()

        self.__lr = Register(LR_ADDRESS, 'LR')
        self.__lr_lock = threading.Lock()

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

        if self.__pcb.quantum > 0:
            self.__pcb.quantum -= 1

        return

    def __str__(self):
        reg_str = '[ '
        for i in range(len(self.__pcb.registers)):
            reg = self.__pcb.registers[i]
            reg_str += '[{dir:d}: {data:d}]'.format(dir=reg.address, data=reg.data)
            if i < len(self.__pcb.registers) - 1:
                reg_str += ','
            reg_str += ' '
        reg_str += ']'
        format_str = '{name:s}:\n\nPC: {pc:d}, LR: {lr:d}\nRegs: {regs:s}'
        return format_str.format(name=self.name, pc=self.__pcb.pc.data, lr=self.__lr.data, regs=reg_str)

