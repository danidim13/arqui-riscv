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
OP_LR_SC = (OpCodes.OP_LR, OpCodes.OP_SC)
OP_BRANCH = (OpCodes.OP_BEQ, OpCodes.OP_BNE)
OP_ROUTINE = (OpCodes.OP_JAL, OpCodes.OP_JALR)


class Register(object):
    """Clase que modela un registro del CPU"""

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
        self.__lr.data = -1
        self.__lr_lock = threading.RLock()

        self.data_cache = None
        self.inst_cache = None
        self.state = self.RUN
        self.log = {}
        self._hits = 0
        self._misses = 0

    def run(self):
        """
        Corre el núcleo hasta que no haya hilillos pendientes de ejecución. Si el quanto es mayor que 0 manda a ejecutar
        la siguiente instrucción, si no hace cambio de contexto del hilillo.

        :return:
        """

        # Obtener primer PCB
        self._pcb_in()
        assert self.__pcb is not None

        while self.state == self.RUN:
            if self.__pcb.quantum > 0:
                self.step()
            else:
                self._context_switch()

    def step(self):
        """
        Ejecuta la siguiente instrucción. Decrementa en uno el quantum o lo pone en cero si la instrucción era FIN

        :return:
        """

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
        """
        Avanza en uno el reloj. Sincroniza con la barrera global.

        :return:
        """
        # logging.debug('Barrier id: {0:d}'.format(id(self.__global_vars.clock_barrier)))
        # logging.debug('%s waiting for clock sync', self.name)
        self.clock += 1
        self._global_vars.clock_barrier.wait()

    def iddle(self):
        """
        No hace nada, pero espera en la barrera. Este método se usa luego de que un procesador ya terminó, mientras
        el otro está corriendo para que no bloquee infinitamente en la barrera que sincroniza los relojes.

        :return:
        """
        logging.debug('%s waiting for clock sync', self.name)
        self._global_vars.clock_barrier.wait()

    def _context_switch(self):
        """
        Maneja el cambio de contexto. Saca el pcb actual y obtiene uno nuevo.

        :return:
        """
        logging.debug('{:s} haciendo CONTEXT SWITCH'.format(self.name))

        self.__lr_lock.acquire()
        self.__lr.data = -1
        self.__lr_lock.release()

        self._pcb_out()
        self._pcb_in()
        self.clock_tick()

    def _pcb_out(self):
        """
        Saca el PCB que estaba ejectuando. Actualiza el número de ciclos corridos y los registos. Si ya terminó lo
        guarda en la cola de terminados del scheduler, si no lo vuelve a guardar en la cola de hilillos en espera

        :return:
        """
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
        """
        Obtiene un nuevo pcb para ejecución y copia el contexto al procesador. Si ya no quedan hilillos cambia el
        estado del procesador a IDL

        :return:
        """

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
        """
        Etapa de fetch del pipeline, obtiene la instrucción y actualiza PC

        :return:    La instucción codificada
        """

        ins, hit = self.inst_cache.load(self.pc.data)

        if not hit:
            logging.info('Miss de instrucción @(0x{:04X})'.format(self.pc.data))

        self.pc.data = self.pc.data+4
        return ins

    def _decode(self, instruction: int):
        """
        Estapa de decode del pipeline, decodifica la instrucción en el código de operación y los argumentos

        :param instruction:     La instucción codificada
        :return:                Código de operación, registro destido, registros fuentes e inmediato, según sea el caso
        """
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
            rd = arg2
            rf1 = arg1
            rf2 = arg2

        elif op_code == OpCodes.OP_FIN or op_code == OpCodes.OP_NOOP:
            pass

        else:
            logging.warning('Unknown OPCODE {:s}'.format(op_code.name))

        return op_code, rd, rf1, rf2, inm

    def _execute(self, op_code: OpCodes, rf1: int, rf2: int, inm: int):
        """
        Etapa de ejecución del pipeline, hace los cálculos de la operación, dirección de acceso a memoria o condición
        del salto.

        :param op_code:     Código de operación
        :param rf1:         Registro fuente
        :param rf2:         Registro fuente
        :param inm:         Valor inmediato
        :return:            Resultado de la operación, dirección de memoria, salto tomado y dirección de salto según sea
                            el caso
        """

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

        elif op_code == OpCodes.OP_LR:
            x1 = self.registers[rf1].data
            self.__lr_lock.acquire()
            self.__lr.data = x1
            self.__lr_lock.release()
            memd = x1

        elif op_code == OpCodes.OP_SC:
            x1 = self.registers[rf1].data
            # x2 = self.registers[rf2].data
            memd = x1

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
        """
        Etapa de acceso a memoria del pipeline, se encarga de hacer load/store y lr/sc

        :param op_code:     Código de operación
        :param memd:        Dirección de memoria
        :param rf2:         Registro fuente (contiene el dato para store)
        :param xd:          Resultado de la ALU, lo sobre escribe con el dato obtenido en load si es el caso
        :return:            Resultado de load o resultado de ALU si el OPCODE no era Load o LR
        """

        if op_code == OpCodes.OP_LW:
            xd, hit = self.data_cache.load(memd)
            assert type(xd) == int
            if not hit:
                logging.info('Miss de lectura @(0x{:04X})'.format(memd))
                self._misses += 1
            else:
                self._hits += 1

        elif op_code == OpCodes.OP_SW:
            word = self.registers[rf2].data
            assert type(word) == int
            hit = self.data_cache.store(memd, word)
            if not hit:
                logging.info('Miss de escritura @(0x{:04X})'.format(memd))
                self._misses += 1
            else:
                self._hits += 1

        elif op_code == OpCodes.OP_LR:
            xd, hit = self.data_cache.load_reserved(memd)
            assert type(xd) == int
            if not hit:
                logging.info('Miss de lectura reservada @(0x{:04X})'.format(memd))
                self._misses += 1
            else:
                self._hits += 1

        elif op_code == OpCodes.OP_SC:

            word = self.registers[rf2].data
            self.__lr_lock.acquire()
            success = self.__lr.data == memd
            self.__lr_lock.release()

            if success:
                hit, success = self.data_cache.store_conditional(memd, word)
                if not hit:
                    logging.info('Miss de escritura condicional @(0x{:04X})'.format(memd))
                    self._misses += 1
                else:
                    self._hits += 1
            else:
                logging.info('Reserva rota @(0x{:04X})'.format(memd))

            if success:
                logging.info('SC success!')
                xd = word
            else:
                logging.info('SC failure!')
                xd = 0

        return xd

    def _write_back(self, op_code, rd, xd, jmp, jmp_target):
        """
        Etapa de writeback del pipeline, escribe al registro destino el resultado de la operación o la carga de datos
        de memoria. También maneja los saltos (a pesar de que esto se puede hacer antes como se vio en la teoría era más
        sencillo para debug hacerlo acá).

        :param op_code:
        :param rd:
        :param xd:
        :param jmp:
        :param jmp_target:
        :return:
        """
        if op_code in OP_ROUTINE or op_code in OP_BRANCH:
            if jmp:
                self.pc.data = jmp_target

        if op_code in OP_ARITH_REG or op_code in OP_ROUTINE or op_code in OP_LR_SC or op_code == OpCodes.OP_ADDI or op_code == OpCodes.OP_LW:
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


        pcb_str = '[\n'
        for k, v in self.log.items():
            pcb_str += ' PID {:02d}: {:d} corridas\n'.format(k, v)

        pcb_str += ']'



        miss_rate = (self._misses) / float(self._hits + self._misses)
        format_str = '{name:s}:\nPC: {pc:d}, LR: {lr:d}, ticks: {clock:d}\nTotal de solicitudes de acceso a memoria:' \
                     ' {total:d}\nTotal de fallos de caché: {miss:d}\nTaza de fallos: {missr:.1f}%\nRegistros:\n' \
                     '{regs:s}\nHilos corridos:\n{hilos:s}\n'

        return format_str.format(name=self.name, pc=self.pc.data, lr=self.__lr.data, clock=self.clock,
                                 regs=reg_str, missr=miss_rate*100, total=(self._hits+self._misses),
                                 miss=self._misses, hilos=pcb_str)

