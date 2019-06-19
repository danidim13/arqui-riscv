import threading
from typing import List, Optional


PC_ADDRESS = 32
LR_ADDRESS = 33


class Register(object):
    __address: int
    __reg_type: str
    __zero_reg: bool
    __data: int

    def __init__(self, address, reg_type, zero_reg=False):
        self.__address = address
        self.__reg_type = reg_type
        self.__zero_reg = zero_reg
        self.__data = 0

    @property
    def data(self):
        if self.__zero_reg:
            return 0
        else:
            return self.__data

    @data.setter
    def data(self, var: int):
        """ Set the register's value
        :type var: int
        """
        if self.__zero_reg:
            raise Exception('Trying to set Zero Register value')
        else:
            self.__data = var


class Pcb(object):
    def __init__(self):
        self.registers = [Register(i, 'General purpose', i == 0) for i in range(32)]
        self.pc = Register(PC_ADDRESS, 'PC')
        self.quantum = 0


class Core(object):
    r"""Clase que modela el núcleo"""
    __registers: List[Register]
    __lr: Register
    __lr_lock: Lock
    __pcb: Optional[Pcb]

    def __init__(self, global_vars):

        self.__global_vars = global_vars
        self.__pcb = Pcb()

        self.__lr = Register(LR_ADDRESS, 'LR')
        self.__lr_lock = threading.Lock()

        self.__data_cache = None
        self.__inst_cache = None

    def set_data_cache(self, cache: object):
        self.__data_cache = cache

    def set_inst_cache(self, cache: object):
        self.__inst_cache = cache

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
        else:
            self.context_switch()

        return


