from __future__ import division

import threading
from typing import List
from .core import Core

FI = 0
FC = 1
FM = 2

CACHE_MISS_PENALTY = 100


class CacheBlock(object):

    def __init__(self, address: int, palabras: int = 4, bpp: int = 4):
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
            flag = 'E'

        return 'B{:d}, tag: {:d}, flag: {:s}, data: {:s}'.format(self.address, self.tag, flag, str(self.data))


class CacheSet(object):
    def __init__(self, index: int, assoc: int, ppb: int):
        self.index = index
        self.assoc = assoc
        self.ppb = ppb
        self.fifo = 0
        self.lines = [CacheBlock(i, ppb) for i in range(assoc)]


class CacheMemAssoc(object):
    """ Clase que modela una memoria cache asociativa """

    def __init__(self, name: str, start_addr: int, end_addr: int, assoc: int, num_blocks: int, bpp: int, ppb: int):
        """
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

        self.lock = threading.Lock()

        self.main_memory: RamMemory = None
        self.owner_core: Core = None

    def __str__(self):

        format_str = '{:s} ({:d}-way associative cache):\n[\n'.format(self.name, self.assoc)
        for set in self.sets:
            set_str = ' S{:d}:\n [\n'.format(set.index)
            for block in set.lines:
                set_str += '   ' + str(block) + '\n'
            set_str += ' ]\n'
            format_str += set_str

        return format_str + ']\n'

    def load(self, addr: int):

        assert self.__start_addr <= addr && addr < self.__end_addr

        block_num, offset, index, tag = self._process_address(addr)

        self.lock.acquire()
        target_block = self._find(index, tag)

        if target_block is None:
            # Miss
            self.lock.release()

            self._wait_penalty(CACHE_MISS_PENALTY)

            self.main_memory.lock.acquire()
            self.lock.acquire()

            target_block = self._fetch(addr)

            word = target_block.data[offset]

            self.lock.release()
            self.main_memory.lock.release()

        else:
            # Hit
            word = target_block.data[offset]
            self.lock.release()

        return word

    def store(self, addr: int, val: int):
        # TODO
        pass

    def load_reserved(self, addr: int):
        # TODO
        pass

    def store_conditional(self, addr: int, val: int):
        # TODO
        pass

    def _process_address(self, addr: int):
        """
        Procesa una dirección de memoria para obtener el número de bloque, index en el caché, offset de palabra y
        tag del bloque.
        :param addr:    Dirección de memoria
        :return:        block, offset, index, tag
        """
        block = addr // (self.ppb * self.bpp)
        offset = (addr % (self.ppb * self.bpp)) // self.bpp
        index = block % self.num_sets
        assert ((block - self.__start_addr) % self.num_sets) == index
        tag = block // self.num_sets

        return block, offset, index, tag

    def _find(self, index: int, tag:int ):

        target = None
        for block in self.sets[index].lines:
            if (block.tag == tag) and (block.flag != FI):
                target = block
                break

        return target

    def _fetch(self, addr: int):

        block_num, offset, index, tag = self._process_address(addr)

        victim_i = self.sets[index].fifo
        victim_b = self.sets[index].lines[victim_i]

        if victim_b.flag == FM:
            # Write Back
            victim_addr = (victim_b.tag + index) * self.ppb * self.bpp
            self.main_memory.set(victim_addr, victim_b)
            victim_b.flag = FI

        # TODO: definir si snooping sucede en get o hay que hacerlo aparte
        # mem_b = self.main_memory.snoop_read(victim_addr)
        mem_b = self.main_memory.get(addr)

        # Sustituir los datos del bloque
        victim_b.data[:] = mem_b.data[:]
        victim_b.tag = tag
        victim_b.flag = FC
        assert len(victim_b.data) == victim_b.palabras

        self.sets[index].fifo = (self.sets[index].fifo + 1) % self.assoc
        return victim_b

    def _wait_penalty(self, clock_cycles: int, waiting_core: Core = None):

        if waiting_core is None:
            waiting_core = self.owner_core

        for i in range(clock_cycles):
            waiting_core.clock_tick()




class RamBlock(object):

    def __init__(self, address: int, palabras: int = 4, bpp: int = 4):
        assert(address % bpp == 0)
        self.address = address

        self.palabras = palabras
        self.bpp = bpp
        self.data = [1 for i in range(palabras)]


class RamMemory(object):

    name: str
    __start_addr: int
    __end_addr: int
    num_blocks: int
    bpp: int
    ppb: int
    blocks: List[RamBlock]
    bus: List[CacheMemAssoc]
    lock: threading.Lock

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

        self.bus = []

        self.lock = threading.Lock()

    def get(self, addr: int) -> RamBlock:
        # TODO
        pass

    def set(self, addr: int, block: CacheBlock):
        # TODO
        pass

    def snoop_read(self, addr: int, requester: CacheMemAssoc):
        # TODO
        pass

