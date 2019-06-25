import threading
import logging
from typing import List, Optional
from .util import GlobalVars
from .isa import OpCodes, decode as isa_decode
from .hilo import Pcb


PC_ADDRESS = 32
LR_ADDRESS = 33

OP_ARITH_REG = (OpCodes.OP_ADD, OpCodes.OP_SUB, OpCodes.OP_MUL, OpCodes.OP_DIV)
OP_LOAD_STORE = (OpCodes.OP_LW, OpCodes.OP_SW)
OP_BRANCH = (OpCodes.OP_BEQ, OpCodes.OP_BNE)
OP_ROUTINE = (OpCodes.OP_JAL, OpCodes.OP_JALR)


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


class Core(object):
    r"""Clase que modela el núcleo"""
    __lr: Register
    __lr_lock: threading.RLock
    __pcb: Optional[Pcb]
    __global_vars: GlobalVars

    RUN = 0
    IDL = 1
    END = 2

    def __init__(self, name: str, global_vars: GlobalVars):

        self.name = name
        self.clock = 0

        self.registers = [Register(i, 'General purpose', i == 0) for i in range(32)]
        self.pc = Register(PC_ADDRESS, 'PC')

        self.__global_vars = global_vars
        self.__pcb = None

        self.__lr = Register(LR_ADDRESS, 'LR')
        self.__lr_lock = threading.RLock()

        self.data_cache = None
        self.inst_cache = None
        self.state = self.RUN

    def fetch(self):

        ins, hit = self.inst_cache.load(self.pc.data)

        if not hit:
            logging.info('Miss de instrucción @(0x{:04X})'.format(self.pc.data))

        self.pc.data = self.pc.data+4
        return ins

    def decode(self, instruction: int):
        op_code, arg1, arg2, arg3 = isa_decode(instruction)
        op_code = OpCodes(op_code)

        rd = None
        rf1 = None
        rf2 = None
        inm = None


        logging.info('Operación {:s}'.format(op_code.name))

        if op_code in OP_ARITH_REG:
            rd = arg1
            rf1 = arg2
            rf2 = arg3
            logging.debug('Ejecutando -->  {:s} r{:02d}, r{:02d}, r{:02d}'.format(op_code.name, rd, rf1, rf2))

        elif op_code in OP_BRANCH or op_code == OpCodes.OP_SW:
            rf1 = arg1
            rf2 = arg2
            inm = arg3

        elif op_code in OP_ROUTINE or op_code == OpCodes.OP_ADDI or op_code == OpCodes.OP_LW:
            rd = arg1
            rf1 = arg2
            inm = arg3

        elif op_code == OpCodes.OP_LR:
            rd = arg1
            rf1 = arg2

        elif op_code == OpCodes.OP_SC:
            rf1 = arg1
            rf2 = arg2

        return op_code, rd, rf1, rf2, inm

    def execute(self, op_code: OpCodes, rf1: int, rf2: int, inm: int):

        # FIXME: xd y memd se pueden fusionar en una sola variable (alu_out)
        xd = None
        memd = None
        jmp = None
        jmp_target = None

        if op_code in OP_ARITH_REG:
            x2 = self.registers[rf1].data
            x3 = self.registers[rf2].data
            if op_code == OpCodes.OP_ADD:
                xd = x2 + x3
            elif op_code == OpCodes.OP_SUB:
                xd = x2 - x3
            elif op_code == OpCodes.OP_MUL:
                xd = x2 * x3
            elif op_code == OpCodes.OP_DIV:
                xd = x2 // x3
            else:
                logging.error('Unexpected OPCODE {:s} in exec '.format(op_code.name))

        elif op_code == OpCodes.OP_ADDI:
            x2 = self.registers[rf1].data
            n = inm
            xd = x2 + n

        elif op_code in OP_LOAD_STORE:
            x1 = self.registers[rf1].data
            n = inm
            memd = x1 + n

        elif op_code in OP_BRANCH:
            x1 = self.registers[rf1].data
            x2 = self.registers[rf2].data
            n = inm

            if op_code == OpCodes.OP_BEQ:
                jmp = x1 == x2
            elif op_code == OpCodes.OP_BNE:
                jmp = x1 != x2
            else:
                logging.error('Unexpected OPCODE {:s} in exec '.format(op_code.name))

            jmp_target = self.pc.data + 4*n

        elif op_code in OP_ROUTINE:
            n = inm
            jmp = True

            if op_code == OpCodes.OP_JAL:
                jmp_target = self.pc.data + n
            elif op_code == OpCodes.OP_JALR:
                x1 = self.registers[rf1].data
                jmp_target = x1 + n
            else:
                logging.error('Unexpected OPCODE {:s} in exec '.format(op_code.name))

            xd = self.pc.data

        assert type(xd) == int or xd is None
        assert type(memd) == int or memd is None
        assert type(jmp_target) == int or jmp_target is None
        assert type(jmp) == bool or jmp is None

        return xd, memd, jmp, jmp_target

    def memory(self, op_code: OpCodes, memd: int, rf2: int, xd: int):

        if op_code == OpCodes.OP_LW:
            xd, hit = self.data_cache.load(memd)
            assert type(xd) == int
            if not hit:
                logging.info('Miss de lectura @(0x{:04X})'.format(memd))

        elif op_code == OpCodes.OP_SW:
            word = self.registers[rf2].data
            assert type(word) == int
            hit = self.data_cache.store(memd, word)
            if not hit:
                logging.info('Miss de escritura @(0x{:04X})'.format(memd))

        elif op_code == OpCodes.OP_LR:
            pass
        elif op_code == OpCodes.OP_SC:
            pass

        return xd

    def write_back(self, op_code, rd, xd, jmp, jmp_target):
        if op_code in OP_ROUTINE or op_code in OP_BRANCH:
            if jmp:
                self.pc.data = jmp_target

        if op_code in OP_ARITH_REG or op_code in OP_ROUTINE or op_code == OpCodes.OP_ADDI or op_code == OpCodes.OP_LW:
            assert type(xd) == int
            self.registers[rd].data = xd

    def step(self):

        # if self.__pcb.quantum > 0:

        ins = self.fetch()
        op_code, rd, rf1, rf2, inm = self.decode(ins)
        xd, memd, jmp, jmp_target = self.execute(op_code, rf1, rf2, inm)
        xd = self.memory(op_code, memd, rf2, xd)
        self.write_back(op_code, rd, xd, jmp, jmp_target)

        if op_code == OpCodes.OP_FIN:
            self.state = self.END
        #     self.__pcb.quantum = 0
        # else:
        #     self.__pcb.quantum -= 1

        #
        # else:
        #     # TODO: Context Switch
        #     pass

        self.clock_tick()

    def clock_tick(self):
        # logging.debug('Barrier id: {0:d}'.format(id(self.__global_vars.clock_barrier)))
        # logging.debug('%s waiting for clock sync', self.name)
        self.__global_vars.clock_barrier.wait()
        self.clock += 1
        #time.sleep(1)

    def __str__(self):

        reg_str = '[\n '

        reg_data_len = max([len(str(reg.data)) for reg in self.registers])

        for i in range(len(self.registers)):
            reg = self.registers[i]
            reg_str += '[r{dir:02d}: {data:{reg_len}d}]'.format(dir=reg.address, data=reg.data, reg_len=reg_data_len)

            if i < len(self.registers) - 1:
                reg_str += ','

                if (i+1)%8 == 0:
                    reg_str +='\n '
                else:
                    reg_str += ' '

        reg_str += '\n]'
        format_str = '{name:s}:\nPC: {pc:d}, LR: {lr:d}, ticks: {clock:d}\nRegs:\n{regs:s}\n'
        return format_str.format(name=self.name, pc=self.pc.data, lr=self.__lr.data, clock=self.clock,
                                 regs=reg_str)

