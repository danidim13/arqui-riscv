

M_OPCD = 0x000000FF
M_ARG1 = 0x00001F00
M_ARG2 = 0x0003E000
M_ARG3 = 0xFFFC0000

assert M_OPCD + M_ARG1 + M_ARG2 + M_ARG3 == 0xFFFFFFFF
assert M_OPCD & M_ARG1 & M_ARG2 & M_ARG3 == 0
assert M_OPCD | M_ARG1 | M_ARG2 | M_ARG3 == 0xFFFFFFFF

BS_OPCD = 0
BS_ARG1 = 8
BS_ARG2 = 13
BS_ARG3 = 18
INS_LENGTH = 32


OP_ADDI = 19

OP_ADD = 71
OP_SUB = 83
OP_MUL = 72
OP_DIV = 56

OP_LW = 5
OP_SW = 37

OP_LR = 51
OP_SC = 52

OP_BEQ = 99
OP_NEQ = 100
OP_JAL = 111
OP_JALR = 103

OP_FIN = 0xFF


def dec_opcode(instruction: int):
    return (instruction & M_OPCD) >> BS_OPCD


def dec_arg1(instruction: int):
    return (instruction & M_ARG1) >> BS_ARG1


def dec_arg2(instruction: int):
    return (instruction & M_ARG2) >> BS_ARG2


def dec_arg3(instruction: int):
    data_raw = (instruction & M_ARG3) >> BS_ARG3
    arg_bits = INS_LENGTH - BS_ARG3

    if data_raw & 2**(arg_bits - 1):
        val = -(2**arg_bits - data_raw)
    else:
        val = data_raw

    return val


def decode(instruction: int):
    op = dec_opcode(instruction)
    arg1 = dec_arg1(instruction)
    arg2 = dec_arg2(instruction)
    arg3 = dec_arg3(instruction)
    return op, arg1, arg2, arg3


def encode(opcode: int, arg1: int, arg2: int, arg3: int):

    arg3_bits = INS_LENGTH - BS_ARG3
    assert 0 <= opcode < 2**8
    assert 0 <= arg1 < 2**5
    assert 0 <= arg2 < 2**5
    assert -2**(arg3_bits-1) <= arg3 < 2**(arg3_bits-1)

    instruction = 0
    instruction |= (opcode & M_OPCD)
    instruction |= (arg1 << BS_ARG1) & M_ARG1
    instruction |= (arg2 << BS_ARG2) & M_ARG2
    instruction |= (arg3 << BS_ARG3) & M_ARG3

    return instruction
