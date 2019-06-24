from __future__ import division

import threading
import logging
import random
from typing import List, Optional
from .core import Core

FI = 0
"""Bandera de inválido en caché"""

FC = 1
"""Bandera de compartido en caché"""

FM = 2
"""Bandera de modificado en caché"""

BUS_DOWNTIME = 2
MEMORY_LOAD_PENALTY = 32


class CacheBlock(object):
    """Clase que modela un bloque de caché"""

    def __init__(self, address: int, palabras: int = 4, bpp: int = 4):
        """
        Crea un bloque de caché, inicializa la memoria con 0s y el tag
        en -1. El tag es el número de bloque.

        :param address:     Dirección del bloque dentro del set de caché
        :param palabras:    Cantidad de palabaras por bloque
        :param bpp:         Bytes por palabra
        """
        self.address = address
        self.tag = -1
        self.flag = FI

        self.palabras = palabras
        self.bpp = bpp
        self.data = [0 for i in range(palabras)]

    def __str__(self):

        if self.flag == FI:
            flag = 'I'
        elif self.flag == FC:
            flag = 'C'
        elif self.flag == FM:
            flag = 'M'
        else:
            flag = 'X'

        return 'B{:d}, tag: {:d}, flag: {:s}, data: {:s}'.format(self.address, self.tag, flag, str(self.data))


class CacheSet(object):
    """Clase que modela un set de bloques de caché en un caché asociativo"""

    def __init__(self, index: int, assoc: int, ppb: int):
        self.index = index
        self.assoc = assoc
        self.ppb = ppb
        self.fifo = 0
        self.lines = [CacheBlock(i, ppb) for i in range(assoc)]


class CacheMemAssoc(object):
    """Clase que modela una memoria caché asociativa"""

    def __init__(self, name: str, start_addr: int, end_addr: int, assoc: int, num_blocks: int, bpp: int, ppb: int):
        """
        Crear una memoria caché asociativa que mappea al rango de direcciones [start_addr, end_addr[

        :param name:        Nombre para identificar la caché
        :param start_addr:  Dirección inicial (inclusiva)
        :param end_addr:    Dirección final (exclusiva)
        :param assoc:       Asociatividad del caché (cantidad de vías)
        :param num_blocks:  Cantidad de bloques que se pueden guardar en caché
        :param bpp:         Bytes por palaba
        :param ppb:         Palabras por bloque
        """

        assert end_addr > start_addr
        assert num_blocks % assoc == 0

        self.name = name
        self.__start_addr = start_addr
        self.__end_addr = end_addr
        self.__start_block = start_addr // (ppb * bpp)

        self.assoc = assoc
        self.num_blocks = num_blocks
        self.num_sets = num_blocks // assoc

        self.bpp = bpp
        self.ppb = ppb

        self.sets = [CacheSet(i, self.assoc, self.ppb) for i in range(self.num_sets)]

        self.lock = threading.RLock()

        self.owner_core: Core = None
        self.bus: Bus = None
        self._alien_core = None

    def __str__(self):

        format_str = '{:s} ({:d}-way associative cache):\n[\n'.format(self.name, self.assoc)
        for set in self.sets:
            set_str = ' S{:d}:\n [\n'.format(set.index)
            for block in set.lines:
                set_str += '   ' + str(block) + '\n'
            set_str += ' ]\n'
            format_str += set_str

        return format_str + ']\n'

    def load(self, addr: int) -> int:
        """
        Carga la palabra de una dirección de memoria. Utiliza el protocolo MSI, en caso de miss accede a bus.
        Si la dirección solicitada no mappea al caché levanta una excepción.

        :param addr:    Dirección de memoria de la palabra solicitada
        :return:        La palabra solicitada
        """
        assert self.__start_addr <= addr < self.__end_addr
        if addr % self.bpp != 0:
            logging.warning('LOAD no alineado @{:d} !'.format(addr))

        block_num, offset, index, tag = self._process_address(addr)

        op_finished = False
        op_local = True
        word = None

        while not op_finished:

            # Sin acceso a bus
            if op_local:

                self._acquire_local()
                target_block = self._find(index, tag)

                # HIT
                if target_block is not None:
                    logging.debug('Read Hit para {:d}, en [set: {:d}, block: {:d}, tag: {:d}] '.format(addr, index, target_block.address, tag))
                    word = target_block.data[offset]
                    op_finished = True

                # MISS
                else:
                    logging.debug('Read Miss para {:d}, en [set: {:d}, tag: {:d}] '.format(addr, index, tag))
                    op_local = False

                self._release_local()

            # Acceso a bus
            else:

                self._wait_penalty(1)
                self._acquire_with_bus()
                target_block = self._find(index, tag)

                # HIT
                if target_block is not None:
                    word = target_block.data[offset]

                # MISS
                else:

                    victim_b = self._find_victim(index)

                    mem_b = self.bus.snoop_shared(addr, self)
                    self._wait_penalty(MEMORY_LOAD_PENALTY)

                    # Sustituir los datos del bloque
                    victim_b.data[:] = mem_b.data[:]
                    victim_b.flag = FC
                    victim_b.tag = block_num
                    assert len(victim_b.data) == victim_b.palabras

                    word = victim_b.data[offset]

                self._release_with_bus()
                op_finished = True

                self._wait_penalty(BUS_DOWNTIME)

        return word

    def store(self, addr: int, val: int):
        assert self.__start_addr <= addr < self.__end_addr
        if addr % self.bpp != 0:
            logging.warning('STORE no alineado @{:d} !'.format(addr))

        block_num, offset, index, tag = self._process_address(addr)

        op_finished = False
        op_local = True
        word = None

        while not op_finished:

            # Sin acceso a bus
            if op_local:

                self._acquire_local()
                target_block = self._find(index, tag)

                # HIT
                if target_block is not None:
                    logging.debug('Write Hit para {:d}, en [set: {:d}, block: {:d}, tag: {:d}]'.format(addr, index, target_block.address, tag))

                    if target_block.flag == FM:
                        target_block.data[offset] = val
                        op_finished = True

                    else:
                        logging.debug('Bloque compartido, se debe invalidar con snooping')
                        op_local = False

                # MISS
                else:
                    logging.debug('Write Miss para {:d}, en [set: {:d}, tag: {:d}]'.format(addr, index, tag))
                    op_local = False

                self._release_local()

            # Acceso a bus
            else:

                self._wait_penalty(1)
                self._acquire_with_bus()

                target_block = self._find(index, tag)

                # HIT
                if target_block is not None:
                    word = target_block.data[offset]
                    logging.debug('Write Hit con bus para {:d}, en [set: {:d}, block: {:d}, tag: {:d}]'.format(addr, index, target_block.address, tag))

                    if target_block.flag == FM:
                        logging.warning('Camino inesperado en Store para {:d}, en [set: {:d}, block: {:d}, tag: {:d}]'.format(addr, index, target_block.address, tag))

                    else:
                        assert target_block.flag == FC
                        logging.debug('Bloque compartido, invalidando por medio de snooping')
                        mem_b = self.bus.snoop_exclusive(addr, self)
                        self._wait_penalty(MEMORY_LOAD_PENALTY)

                    target_block.data[offset] = val
                    target_block.flag = FM

                # MISS
                else:

                    victim_b = self._find_victim(index)

                    mem_b = self.bus.snoop_exclusive(addr, self)
                    self._wait_penalty(MEMORY_LOAD_PENALTY)

                    # Sustituir los datos del bloque
                    victim_b.data[:] = mem_b.data[:]
                    victim_b.flag = FM
                    victim_b.tag = block_num
                    assert len(victim_b.data) == victim_b.palabras

                    victim_b.data[offset] = val

                self._release_with_bus()
                op_finished = True

                self._wait_penalty(BUS_DOWNTIME)

        return

    def load_reserved(self, addr: int):
        # TODOCacheBlock
        pass

    def store_conditional(self, addr: int, val: int):
        # TODO
        pass

    def acquire_external(self, requester: Core):
        """
        Intenta bloquear la caché para uso externo (a través del bus)

        :type requester: El procesador que está ejecutando la operación
        """
        assert requester is not self.owner_core
        self._acquire_local(waiting_core=requester)
        self._alien_core = requester

    def snoop_find(self, addr: int) -> Optional[CacheBlock]:
        """
        Busca si una dirección se encuentra en el caché. Este método debe usarse en conjunto con ``acquire_external()``
        y ``release_external()``.

        :param addr:    La dirección que se busca
        :return:        El bloque si está en caché, None en caso contrario
        """
        block_num, offset, index, tag = self._process_address(addr)
        target_block = self._find(index, tag)
        return target_block

    def release_external(self, requester: Core):
        """
        Libera la caché luego de un uso externo (a través del bus)

        :type requester: El procesador que bloqueó la caché originalmente
        """
        assert requester is not self.owner_core
        assert requester is self._alien_core
        self._alien_core = None
        self._release_local()

    def _process_address(self, addr: int):
        """
        Procesa una dirección de memoria para obtener el número de bloque, index en el caché y offset de palabra.

        :param addr:    Dirección de memoria
        :return:        block, offset, index, tag
        """
        block = addr // (self.ppb * self.bpp)
        offset = (addr % (self.ppb * self.bpp)) // self.bpp
        index = block % self.num_sets
        assert ((block - self.__start_addr // (self.ppb*self.bpp)) % self.num_sets) == index
        # tag = block // self.num_sets
        tag = block

        logging.debug('accediendo a dir {:d}, blocknum={:d}, index={:d}, word_off={:d}, tag={:d}'.format(addr, block, index, offset, tag))
        return block, offset, index, tag

    def _find(self, index: int, tag: int):
        """
        Busca si un bloque se encuentra actualmente en caché

        :param index:   Índice del set en el cual se encuentra el bloque
        :param tag:     Tag del bloque que se está buscando
        :return:        El bloque buscado en caso de hit, None en caso contrario
        """
        target = None
        for block in self.sets[index].lines:
            if (block.tag == tag) and (block.flag != FI):
                target = block
                break

        return target

    def _find_victim(self, index: int):
        """
        Se encarga de seleccionar el bloque víctima y hacer write back (evict) de ser necesario.
        :param index:   Index del set donde se va a seleccionar la vítima
        :return:        Bloque de caché seleccionado ya evacuado
        """

        victim_i = self.sets[index].fifo
        victim_b = self.sets[index].lines[victim_i]

        if victim_b.flag == FM:
            # Write Back
            # victim_b_num = victim_b.tag + index
            victim_b_num = victim_b.tag
            victim_addr = victim_b_num * self.ppb * self.bpp
            self.bus.write_back(victim_addr, victim_b, self)
            self._wait_penalty(MEMORY_LOAD_PENALTY)

        self.sets[index].fifo = (victim_i + 1) % self.assoc
        victim_b.flag = FI
        return victim_b

    def _wait_penalty(self, clock_cycles: int, waiting_core: Core = None):
        """
        Espera cierta cantidad de ciclos de reloj (en caso de Miss p.e.)

        :param clock_cycles:    Ciclos de reloj que espera
        :param waiting_core:    Procesador que debe esperar, si no se indica asume el dueño del caché
        """
        if waiting_core is None:
            waiting_core = self.owner_core

        for i in range(clock_cycles):
            waiting_core.clock_tick()

    def _acquire_local(self, waiting_core: Core = None):

        if waiting_core is None:
            waiting_core = self.owner_core

        while True:

            got_lock = self.lock.acquire(False)

            if got_lock:
                logging.debug('Got cache lock')
                break

            waiting_core.clock_tick()

        return

    def _acquire_with_bus(self, waiting_core: Core = None):

        if waiting_core is None:
            waiting_core = self.owner_core

        while True:

            bus_locked = self.bus.lock.acquire(False)

            if bus_locked:
                logging.debug('Got bus lock')
                cache_locked = self.lock.acquire(False)

                if cache_locked:
                    logging.debug('Got cache lock')
                    break

                logging.debug('Giving up bus lock')
                self.bus.lock.release()

            waiting_core.clock_tick()

        return

    def _release_local(self):
        logging.debug('Releasing cache lock')
        self.lock.release()
        return

    def _release_with_bus(self):
        logging.debug('Releasing bus and cache lock')
        self.lock.release()
        self.bus.lock.release()
        return


class RamBlock(object):

    def __init__(self, address: int, palabras: int = 4, bpp: int = 4):
        assert(address % bpp == 0)
        self.address = address

        self.palabras = palabras
        self.bpp = bpp
        self.data = [1 for i in range(palabras)]

    def __str__(self):
        return 'B{:02d}, data: {:s}'.format(self.address//(self.bpp*self.palabras), str(self.data))


class RamMemory(object):

    blocks: List[RamBlock]

    def __init__(self, name: str, start_addr: int, end_addr: int, num_blocks: int, bpp: int, ppb: int):
        """
        :param name:        Nombre de la memoria
        :param start_addr:  Dirección inicial (inclusiva)
        :param end_addr:    Dirección final (exclusiva)
        :param num_blocks:  Número de bloques en la memoria
        :param bpp:         Bytes por palabra
        :param ppb:         Palabras por bloque
        """

        self.name = name

        assert end_addr > start_addr
        assert start_addr + num_blocks*ppb*bpp == end_addr
        self.__start_addr = start_addr
        self.__end_addr = end_addr
        self.num_blocks = num_blocks
        self.bpp = bpp
        self.ppb = ppb

        self.blocks = [RamBlock(i*ppb*bpp + start_addr, ppb, bpp) for i in range(num_blocks)]

    def get(self, addr: int) -> RamBlock:
        return self._find(addr)

    def set(self, addr: int, cache_block: CacheBlock):
        assert self.ppb == len(cache_block.data)
        assert self.bpp == cache_block.bpp
        block = self._find(addr)
        block.data[:] = cache_block.data[:]
        return

    def load(self, addr: int, data: List[int]):
        bn_i = (addr - self.__start_addr) // (self.ppb * self.bpp)
        off_i = ((addr - self.__start_addr) % (self.ppb * self.bpp)) // self.bpp

        logging.debug('Copying {:d} words into memory starting @ 0x{:04X}, [block {:d} offset {:d}]'.format(len(data), addr, bn_i, off_i))
        for datum in data:

            self.blocks[bn_i].data[off_i] = datum
            off_i += 1

            if off_i >= self.ppb:
                off_i = 0
                bn_i += 1

        last_addr = self.__start_addr + bn_i*self.ppb*self.bpp + (off_i-1)*self.bpp
        logging.debug('Finished copying last address @ 0x{:04X},  next = [block {:d} offset {:d}]'.format(last_addr, bn_i, off_i))

    def _find(self, addr: int):
        assert self.__start_addr <= addr < self.__end_addr

        block_num = (addr - self.__start_addr) // (self.ppb * self.bpp)
        block = self.blocks[block_num]
        assert block.address <= addr < block.address + self.bpp * self.ppb
        return block

    def __str__(self):

        format_str = '{:s} :\n[\n'.format(self.name)
        for block in self.blocks:
            format_str += ' 0x{:04X}: [{:s}]\n'.format(block.address, str(block))

        return format_str + ']\n'


class Bus(object):
    """Clase que modela un bus compartido que conecta varias cachés a una memoria principal"""

    def __init__(self, name: str, memory: RamMemory, caches: List[CacheMemAssoc]):

        self.name = name
        self.__memory = memory
        self.__caches = caches
        self.lock = threading.RLock()

        for cache in caches:
            cache.bus = self

    def snoop_shared(self, addr: int, requester: CacheMemAssoc) -> RamBlock:
        assert requester in self.__caches

        block = None

        for cache in self.__caches:

            if cache is requester:
                logging.debug('Skipping calling cache')
                continue

            cache.acquire_external(requester.owner_core)
            cache_block = cache.snoop_find(addr)

            if cache_block:
                logging.debug('Snoop hit @{:d} en caché {:s}'.format(addr, cache.name))

                if cache_block.flag == FM:
                    logging.debug('Snooped dirty block')
                    self.__memory.set(addr, cache_block)
                    cache_block.flag = FC

                aligned_addr = cache_block.tag * (cache_block.bpp * cache_block.palabras)
                block = RamBlock(address=aligned_addr, palabras=cache_block.palabras, bpp=cache_block.bpp)
                block.data[:] = cache_block.data[:]
                cache.release_external(requester.owner_core)
                break

            else:
                cache.release_external(requester.owner_core)

        if block is None:

            logging.debug('Snoop miss @{:d} defaulting to memory'.format(addr))
            block = self.__memory.get(addr)

        return block

    def snoop_exclusive(self, addr: int, requester: CacheMemAssoc) -> RamBlock:
        assert requester in self.__caches

        block = None

        for cache in self.__caches:

            if cache is requester:
                logging.debug('Skipping calling cache')
                continue

            cache.acquire_external(requester.owner_core)
            cache_block = cache.snoop_find(addr)

            if cache_block:
                # Hit
                logging.debug('Snoop Exclusive hit @{:d} en caché {:s}'.format(addr, cache.name))

                if cache_block.flag == FM:
                    logging.debug('Snooped dirty block, invalidating')
                    self.__memory.set(addr, cache_block)
                    cache_block.flag = FI
                    aligned_addr = cache_block.tag * (cache_block.bpp * cache_block.palabras)
                    block = RamBlock(address=aligned_addr, palabras=cache_block.palabras, bpp=cache_block.bpp)
                    block.data[:] = cache_block.data[:]
                    cache.release_external(requester.owner_core)
                    break

                else:
                    logging.debug('Snooped shared block, invalidating')
                    assert cache_block.flag == FC
                    cache_block.flag = FI

            else:
                # Miss
                cache.release_external(requester.owner_core)

        if block is None:

            logging.debug('Snoop Exclusive miss @{:d} defaulting to memory'.format(addr))
            block = self.__memory.get(addr)

        return block

    def write_back(self, addr: int, block: CacheBlock, requester: CacheMemAssoc):
        logging.debug('Write back requested by for address {:d}, block: [{:s}]'.format(addr, str(block), hex(id(requester))))
        self.__memory.set(addr, block)
        return

    def __str__(self):
        caches_dirs = [hex(id(cache)) for cache in self.__caches]
        format_str = '{:s}: [Memoria: {:s}, Cachés: {:s}]'.format(self.name, hex(id(self.__memory)), str(caches_dirs))
        return format_str
