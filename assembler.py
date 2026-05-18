"""MIPS 汇编器：将文本指令解析为内部表示"""

import re
from typing import Optional


def parse_register(token: str) -> int:
    """解析 rN 或 $N 或 $zero / r0 → 寄存器编号"""
    token = token.strip()
    if token in ("$zero", "r0"):
        return 0
    m = re.match(r'[r\$](\d+)', token)
    if not m:
        raise ValueError(f"无效的寄存器: {token}")
    num = int(m.group(1))
    if not (0 <= num <= 31):
        raise ValueError(f"寄存器编号越界: {num}")
    return num


def parse_offset_imm(token: str) -> int:
    """解析立即数/偏移量，支持十六进制和十进制"""
    token = token.strip()
    if token.lower().startswith('0x'):
        return int(token, 16)
    # 允许负数
    val = int(token)
    return val & 0xFFFFFFFF


def parse_line(line: str) -> Optional[dict]:
    """
    解析一行 MIPS 指令文本 → 内部表示 dict
    格式:
      add  $rd, $rs, $rt
      lw   $rt, offset($rs)
      sw   $rt, offset($rs)
      beqz $rs, offset
    返回 None 表示空行或注释行
    """
    line = line.strip()
    if not line or line.startswith('#'):
        return None

    # 拆分解指令名和操作数
    parts = line.split(maxsplit=1)
    if len(parts) < 2:
        raise ValueError(f"指令格式错误: {line}")
    op = parts[0].lower()
    operands = parts[1]

    if op == 'add':
        # add rd, rs, rt
        m = re.match(r'\s*([r\$]\w+)\s*,\s*([r\$]\w+)\s*,\s*([r\$]\w+)\s*$', operands)
        if not m:
            raise ValueError(f"add 指令格式错误: {line}（正确格式: add rd, rs, rt）")
        rd = parse_register(m.group(1))
        rs = parse_register(m.group(2))
        rt = parse_register(m.group(3))
        return {"op": "add", "rd": rd, "rs": rs, "rt": rt, "imm": None, "text": line}

    elif op == 'lw':
        # lw rt, offset(rs)
        m = re.match(r'\s*([r\$]\w+)\s*,\s*([-\w]+)\s*\(\s*([r\$]\w+)\s*\)\s*$', operands)
        if not m:
            raise ValueError(f"lw 指令格式错误: {line}（正确格式: lw rt, offset(rs)）")
        rt = parse_register(m.group(1))
        imm = parse_offset_imm(m.group(2))
        rs = parse_register(m.group(3))
        return {"op": "lw", "rt": rt, "rs": rs, "imm": imm, "rd": None, "text": line}

    elif op == 'sw':
        # sw rt, offset(rs)
        m = re.match(r'\s*([r\$]\w+)\s*,\s*([-\w]+)\s*\(\s*([r\$]\w+)\s*\)\s*$', operands)
        if not m:
            raise ValueError(f"sw 指令格式错误: {line}（正确格式: sw rt, offset(rs)）")
        rt = parse_register(m.group(1))
        imm = parse_offset_imm(m.group(2))
        rs = parse_register(m.group(3))
        return {"op": "sw", "rt": rt, "rs": rs, "imm": imm, "rd": None, "text": line}

    elif op == 'addi':
        # addi rt, rs, imm
        m = re.match(r'\s*([r\$]\w+)\s*,\s*([r\$]\w+)\s*,\s*([-\w]+)\s*$', operands)
        if not m:
            raise ValueError(f"addi 指令格式错误: {line}（正确格式: addi rt, rs, imm）")
        rt = parse_register(m.group(1))
        rs = parse_register(m.group(2))
        imm = parse_offset_imm(m.group(3))
        return {"op": "addi", "rt": rt, "rs": rs, "imm": imm, "rd": None, "text": line}

    elif op == 'beqz':
        # beqz rs, offset
        m = re.match(r'\s*([r\$]\w+)\s*,\s*([-\w]+)\s*$', operands)
        if not m:
            raise ValueError(f"beqz 指令格式错误: {line}（正确格式: beqz rs, offset）")
        rs = parse_register(m.group(1))
        imm = parse_offset_imm(m.group(2))
        return {"op": "beqz", "rs": rs, "imm": imm, "rd": None, "rt": None, "text": line}

    else:
        raise ValueError(f"不支持的指令: {op}（仅支持 add, addi, lw, sw, beqz）")


def parse_program(code: str) -> list[dict]:
    """解析多行程序文本，返回指令列表"""
    instructions = []
    for i, line in enumerate(code.strip().split('\n')):
        try:
            instr = parse_line(line)
            if instr is not None:
                instructions.append(instr)
        except ValueError as e:
            raise ValueError(f"第{i + 1}行: {e}")
    return instructions
