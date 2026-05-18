"""MIPS32 数据通路：寄存器堆、内存、ALU、PC"""

from typing import Optional


class RegisterFile:
    """32个32位通用寄存器，$0 恒为 0"""

    def __init__(self):
        self.regs = [0] * 32

    def read(self, reg_num: int) -> int:
        if reg_num == 0:
            return 0
        return self.regs[reg_num]

    def write(self, reg_num: int, value: int):
        if reg_num != 0:
            self.regs[reg_num] = value & 0xFFFFFFFF

    def dump(self) -> dict:
        return {i: self.regs[i] for i in range(32)}


class InstructionMemory:
    """指令内存：按字节地址索引，每条指令4字节"""

    def __init__(self):
        self.mem = {}

    def load(self, instructions: list):
        """载入指令列表，每条指令按 4 字节地址递增存储"""
        self.mem = {}
        for i, instr in enumerate(instructions):
            self.mem[i * 4] = instr

    def fetch(self, addr: int) -> Optional[dict]:
        return self.mem.get(addr)


class DataMemory:
    """数据内存：按字节地址索引，支持 lw/sw"""

    def __init__(self, size=1024):
        self.mem = [0] * (size // 4)
        self.access_log = set()

    def _check_addr(self, addr: int):
        if addr % 4 != 0:
            raise ValueError(f"地址 {addr} 未对齐")
        idx = addr // 4
        if idx < 0 or idx >= len(self.mem):
            raise ValueError(f"地址 {addr} 越界")
        return idx

    def read(self, addr: int) -> int:
        idx = self._check_addr(addr)
        self.access_log.add(addr)
        return self.mem[idx]

    def write(self, addr: int, value: int):
        idx = self._check_addr(addr)
        self.access_log.add(addr)
        self.mem[idx] = value & 0xFFFFFFFF

    def dump(self) -> dict:
        return {addr: self.read(addr) for addr in sorted(self.access_log)}


class ALU:
    """算术逻辑单元：add / sub"""

    @staticmethod
    def add(a: int, b: int) -> int:
        return (a + b) & 0xFFFFFFFF

    @staticmethod
    def sub(a: int, b: int) -> int:
        return (a - b) & 0xFFFFFFFF


class PC:
    """程序计数器"""

    def __init__(self):
        self.value = 0

    def get(self) -> int:
        return self.value

    def set(self, addr: int):
        self.value = addr & 0xFFFFFFFF

    def next(self):
        self.value += 4
