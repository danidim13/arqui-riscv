import threading
import logging
from queue import Empty
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
    _global_vars: GlobalVars

    RUN = 0
    IDL = 1
    END = 2

    def __init__(self, name: str, global_vars: GlobalVars):

        self.name = name
        self.clock = 0
        self.pcb_start_clock = 0

        self.registers = [Register(i, 'General purpose', i == 0) for i in range(32)]
        self.pc = Register(PC_ADDRESS, 'PC')

        self._global_vars = global_vars
        self.__pcb = None

        self.__lr = Register(LR_ADDRESS, 'LR')
        self.__lr_lock = threading.RLock()

        self.data_cache = None
        self.inst_cache = None
        self.state = self.RUN
        self.log = {}

    def run(self):

        # Obtener primer PCB
        self._pcb_in()
        assert self.__pcb is not None

        while self.state == self.RUN:
            if self.__pcb.quantum > 0:
                self.step()
            else:
                self._context_switch()

    def step(self):

        ins = self._fetch()
        op_code, rd, rf1, rf2, inm = self._decode(ins)
        xd, memd, jmp, jmp_target = self._execute(op_code, rf1, rf2, inm)
        xd = self._memory(op_code, memd, rf2, xd)
        self._write_back(op_code, rd, xd, jmp, jmp_target)

        if op_code == OpCodes.OP_FIN:
            self.__pcb.status = Pcb.FINISHED
            self.__pcb.quantum = 0
        else:
            self.__pcb.quantum -= 1

        self.clock_tick()

    def clock_tick(self):
        # logging.debug('Barrier id: {0:d}'.format(id(self.__global_vars.clock_barrier)))
        logging.debug('%s waiting for clock sync', self.name)
        self.clock += 1
        self._global_vars.clock_barrier.wait()

    def iddle(self):
        logging.debug('%s waiting for clock sync', self.name)
        self._global_vars.clock_barrier.wait()

    def _context_switch(self):
        logging.debug('{:s} haciendo CONTEXT SWITCH'.format(self.name))
        self._pcb_out()
        self._pcb_in()
        self.clock_tick()

    def _pcb_out(self):
        assert self.__pcb is not None
        assert self.__pcb.quantum == 0

        logging.info('El hilillo {:s} va de salida'.format(self.__pcb.name))
        pcb_ticks = self.clock - self.pcb_start_clock
        self.__pcb.ticks += pcb_ticks
        self.__pcb.pc = self.pc.data
        assert len(self.__pcb.registers) == len(self.registers)
        self.__pcb.registers[:] = [r.data for r in self.registers]

        if self.__pcb.status == Pcb.FINISHED:
            logging.info('El hillilo {:s} terminó de correr'.format(self.__pcb.name))
            self._global_vars.scheduler.put_finished(self.__pcb)
        else:
            assert self.__pcb.status == Pcb.RUNNING
            self.__pcb.status = Pcb.READY
            self._global_vars.scheduler.put_ready(self.__pcb)

        self.__pcb = None

    def _pcb_in(self):

        assert self.__pcb is None

        try:
            self.__pcb = self._global_vars.scheduler.next_ready_thread()
            got_pcb = True

        except Empty as e:
            logging.debug('No se consiguio hilo' + str(e))
            got_pcb = False

        if got_pcb:

            assert self.__pcb.status == Pcb.READY
            self.__pcb.status = Pcb.RUNNING
            self.pcb_start_clock = self.clock

            # Copiar el estado del procesador
            self.pc.data = self.__pcb.pc
            assert len(self.__pcb.registers) == len(self.registers)
            for i in range(1, len(self.registers)):
                self.registers[i].data = self.__pcb.registers[i]

            self.state = self.RUN

            if self.__pcb.pid in self.log.keys():
                self.log[self.__pcb.pid] += 1
            else:
                self.log[self.__pcb.pid] = 1

            logging.info('El hilillo {:s} viene entrando'.format(self.__pcb.name))

        else:
            logging.info('No hay más hilillos pendientes de ejecución')
            self.state = self.IDL

    def _fetch(self):

        ins, hit = self.inst_cache.load(self.pc.data)

        if not hit:
            logging.info('Miss de instrucción @(0x{:04X})'.format(self.pc.data))

        self.pc.data = self.pc.data+4
        return ins

    def _decode(self, instruction: int):
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
            # logging.debug('Ejecutando -->  {:s} r{:02d}, r{:02d}, r{:02d}'.format(op_code.name, rd, rf1, rf2))

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

        elif op_code == OpCodes.OP_FIN or op_code == OpCodes.OP_NOOP:
            pass

        else:
            logging.warning('Unknown OPCODE {:s}'.format(op_code.name))

        return op_code, rd, rf1, rf2, inm

    def _execute(self, op_code: OpCodes, rf1: int, rf2: int, inm: int):

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

    def _memory(self, op_code: OpCodes, memd: int, rf2: int, xd: int):

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

    def _write_back(self, op_code, rd, xd, jmp, jmp_target):
        if op_code in OP_ROUTINE or op_code in OP_BRANCH:
            if jmp:
                self.pc.data = jmp_target

        if op_code in OP_ARITH_REG or op_code in OP_ROUTINE or op_code == OpCodes.OP_ADDI or op_code == OpCodes.OP_LW:
            assert type(xd) == int
            self.registers[rd].data = xd

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

