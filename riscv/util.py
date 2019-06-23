import threading


class GlobalVars(object):

    def __init__(self, num_cpus: int):
        self.clock_barrier = threading.Barrier(parties=num_cpus)

        self.done = False
