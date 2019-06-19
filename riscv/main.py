import threading
import logging
import time


def run_cpu():
    logging.info('Starting thread %s', threading.current_thread().getName())
    time.sleep(5)
    logging.info('Thread ending %s', threading.current_thread().getName())


def main():
    format = "%(asctime)s: %(message)s"

    logging.basicConfig(format=format, level=logging.INFO, datefmt="%H:%M:%S")

    # TODO: create data structures

    # Spawn child Threads
    t_cpu0 = threading.Thread(target=run_cpu, name='CPU0')
    t_cpu1 = threading.Thread(target=run_cpu, name='CPU1')

    t_cpu0.start()
    t_cpu1.start()

    logging.info('Thread {} spawned children'.format(threading.current_thread().getName()))

    t_cpu0.join()
    t_cpu1.join()
    time.sleep(1)


if __name__ == '__main__':
    main()
