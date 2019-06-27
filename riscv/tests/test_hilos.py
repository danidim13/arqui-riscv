import unittest
from riscv import core, memory, util, hilo
from typing import List, Tuple


class SingleCoreTestCase(unittest.TestCase):

    def setUp(self):

        global_vars = util.GlobalVars(1)

        mem_data = memory.RamMemory('Memoria de datos', start_addr=0, end_addr=384, num_blocks=24, bpp=4, ppb=4)
        mem_inst = memory.RamMemory('Memoria de instrucciones', start_addr=384, end_addr=1024, num_blocks=40, bpp=4, ppb=4)
        core0 = core.Core('CPU0', global_vars)
        cache_inst0 = memory.CacheMemAssoc('Inst$0', start_addr=384, end_addr=1024, assoc=1, num_blocks=8, bpp=4, ppb=4)
        cache_data0 = memory.CacheMemAssoc('Data$0', start_addr=0, end_addr=384, assoc=4, num_blocks=8, bpp=4, ppb=4)
        core1 = core.Core('CPU1', global_vars)
        cache_inst1 = memory.CacheMemAssoc('Inst$1', start_addr=384, end_addr=1024, assoc=1, num_blocks=8, bpp=4, ppb=4)
        cache_data1 = memory.CacheMemAssoc('Data$1', start_addr=0, end_addr=384, assoc=1, num_blocks=8, bpp=4, ppb=4)

        core0.inst_cache = cache_inst0
        core0.data_cache = cache_data0
        cache_inst0.owner_core = core0
        cache_data0.owner_core = core0

        core1.inst_cache = cache_inst1
        core1.data_cache = cache_data1
        cache_inst1.owner_core = core1
        cache_data1.owner_core = core1

        bus_inst = memory.Bus('Bus de instucciones', memory=mem_inst, caches=[cache_inst0, cache_inst1])
        bus_data = memory.Bus('Bus de datos', memory=mem_data, caches=[cache_data0, cache_data1])

        self.core0 = core0
        self.cache_inst0 = cache_inst0
        self.cache_data0 = cache_data0
        self.core1 = core1
        self.cache_inst1 = cache_inst1
        self.cache_data1 = cache_data1
        self.mem_data = mem_data
        self.mem_inst = mem_inst
        self.bus_inst = bus_inst
        self.bus_data = bus_data
        self.global_vars = global_vars

    def TearDown(self):

        del self.core0
        del self.cache_inst0
        del self.cache_data0
        del self.core1
        del self.cache_inst1
        del self.cache_data1
        del self.mem_data
        del self.mem_inst
        del self.bus_inst
        del self.bus_data
        del self.global_vars

    def assertRegsEqual(self, core_inst: core.Core, reg_state: List[Tuple[int, int]]):

        for t in reg_state:
            r_dir, r_val = t
            self.assertEqual(core_inst.registers[r_dir].data, r_val)

    def test_hilo11(self):

        path = 'hilos/11.txt'
        instrucciones = util.read_hilo(path)
        self.mem_inst.load(384, instrucciones)
        pcb = hilo.Pcb(name=path)
        self.global_vars.scheduler.put_ready(pcb)

        self.core0.run()

        expected_regs = [(3, 5), (4, 200), (8, 8), (20, 2)]

        for t in expected_regs:
            r_dir, r_val = t
            self.assertEqual(self.core0.registers[r_dir].data, r_val, "Unexpected register value in r{:02d}".format(r_dir))


    def test_hilo12(self):

        path = 'hilos/12.txt'
        instrucciones = util.read_hilo(path)
        self.mem_inst.load(384, instrucciones)
        pcb = hilo.Pcb(name=path)
        self.global_vars.scheduler.put_ready(pcb)

        self.core0.run()

        expected_regs = [(2, 2), (4, 99), (5, 99), (8, 132), (10, 99), (21, 10), (22, 12), (23, 6)]

        for t in expected_regs:
            r_dir, r_val = t
            self.assertEqual(self.core0.registers[r_dir].data, r_val, "Unexpected register value in r{:02d}".format(r_dir))


