"""MIPS 5段流水线模拟器核心"""

from dataclasses import dataclass, field
from typing import Optional
from datapath import RegisterFile, InstructionMemory, DataMemory, PC, ALU


@dataclass
class PipelineReg:
    """段间寄存器基类"""

    def clear(self):
        for f in self.__dataclass_fields__:
            setattr(self, f, None)


@dataclass
class IF_ID(PipelineReg):
    pc_plus_4: int = 0
    instruction: Optional[dict] = None
    instr_addr: int = 0


@dataclass
class ID_EX(PipelineReg):
    pc_plus_4: int = 0
    reg_a: int = 0
    reg_b: int = 0
    imm: int = 0
    rd: Optional[int] = None
    rs: Optional[int] = None
    rt: Optional[int] = None
    op: Optional[str] = None
    instr_addr: int = 0
    reg_write: bool = False
    mem_read: bool = False
    mem_write: bool = False
    alu_src: bool = False
    reg_dst: bool = False
    mem_to_reg: bool = False
    branch: bool = False


@dataclass
class EX_MEM(PipelineReg):
    alu_result: int = 0
    reg_b: int = 0
    rd: Optional[int] = None
    op: Optional[str] = None
    instr_addr: int = 0
    reg_write: bool = False
    mem_read: bool = False
    mem_write: bool = False
    mem_to_reg: bool = False


@dataclass
class MEM_WB(PipelineReg):
    mem_data: int = 0
    alu_result: int = 0
    rd: Optional[int] = None
    op: Optional[str] = None
    instr_addr: int = 0
    reg_write: bool = False
    mem_to_reg: bool = False


@dataclass
class StageState:
    """单个流水段在当前周期的状态"""
    instr: Optional[str] = None
    pc: Optional[int] = None
    bubble: bool = True


@dataclass
class PerformanceStats:
    total_cycles: int = 0
    completed_instructions: int = 0
    data_stalls: int = 0
    load_use_stalls: int = 0
    control_stalls: int = 0
    forwarding_saved: int = 0

    @property
    def cpi(self) -> float:
        if self.completed_instructions == 0:
            return 0.0
        return round(self.total_cycles / self.completed_instructions, 2)


class PipelineSimulator:
    """MIPS 5段流水线模拟器"""

    def __init__(self):
        self.regfile = RegisterFile()
        self.imem = InstructionMemory()
        self.dmem = DataMemory()
        self.pc = PC()

        # 段间寄存器
        self.if_id = IF_ID()
        self.id_ex = ID_EX()
        self.ex_mem = EX_MEM()
        self.mem_wb = MEM_WB()

        # 状态
        self.cycle = 0
        self.instructions: list[dict] = []  # 原始指令列表
        self.forwarding_on = True
        self.running = False
        self.paused_by: Optional[str] = None

        # 断点
        self.pc_breakpoints: set[int] = set()
        self.stage_breakpoints: set[str] = set()

        # 统计
        self.stats = PerformanceStats()

        # 事件日志
        self.events: list[str] = []

        # 冒险控制标志
        self._stall_pc = False
        self._flush_id = False
        self._id_instruction: Optional[dict] = None  # ID段当前处理的指令（用于stall显示）

        # 前递事件追踪（用于时空图箭头）
        self._fwd_events: list[dict] = []

        # 前一周期 MEM/WB（用于 WB 段显示 + 前递）
        self._prev_mem_wb_op: Optional[str] = None
        self._prev_mem_wb_instr_addr: int = 0
        self._prev_mem_wb_alu_result: int = 0
        self._prev_mem_wb_rd: Optional[int] = None
        self._prev_mem_wb_reg_write: bool = False
        self._prev_mem_wb_mem_to_reg: bool = False

        # 每条指令的跟踪信息
        self.instr_tracking: dict[int, dict] = {}  # addr → state

    # ─── 程序加载 ──────────────────────────────

    def load_program(self, instructions: list[dict]):
        """载入指令列表到指令内存"""
        self.reset()
        self.instructions = instructions
        self.imem.load(instructions)
        self.instr_tracking = {}
        for i, instr in enumerate(instructions):
            addr = i * 4
            self.instr_tracking[addr] = {
                "text": instr["text"],
                "stage": None,
                "done": False,
                "flushed": False,
            }

    def reset(self):
        """重置模拟器"""
        self.regfile = RegisterFile()
        self.dmem = DataMemory()
        self.pc = PC()
        self.if_id = IF_ID()
        self.id_ex = ID_EX()
        self.ex_mem = EX_MEM()
        self.mem_wb = MEM_WB()
        self.cycle = 0
        self.instructions = []
        self.instr_tracking = {}
        self.running = False
        self.paused_by = None
        self.stats = PerformanceStats()
        self.events = []
        self._stall_pc = False
        self._flush_id = False
        self._fwd_events = []
        self._prev_mem_wb_op = None
        self._prev_mem_wb_instr_addr = 0
        self._prev_mem_wb_alu_result = 0
        self._prev_mem_wb_rd = None
        self._prev_mem_wb_reg_write = False
        self._prev_mem_wb_mem_to_reg = False
        self._prev_mem_wb_mem_data = 0

    # ─── 控制信号生成 ──────────────────────────

    def _gen_controls(self, instr: dict) -> dict:
        """根据指令生成控制信号"""
        op = instr["op"]
        if op == "add":
            return {"reg_write": True, "mem_read": False, "mem_write": False,
                     "alu_src": False, "reg_dst": True, "mem_to_reg": False,
                     "branch": False}
        elif op == "lw":
            return {"reg_write": True, "mem_read": True, "mem_write": False,
                     "alu_src": True, "reg_dst": False, "mem_to_reg": True,
                     "branch": False}
        elif op == "sw":
            return {"reg_write": False, "mem_read": False, "mem_write": True,
                     "alu_src": True, "reg_dst": False, "mem_to_reg": False,
                     "branch": False}
        elif op == "addi":
            return {"reg_write": True, "mem_read": False, "mem_write": False,
                     "alu_src": True, "reg_dst": False, "mem_to_reg": False,
                     "branch": False}
        elif op == "beqz":
            return {"reg_write": False, "mem_read": False, "mem_write": False,
                     "alu_src": False, "reg_dst": False, "mem_to_reg": False,
                     "branch": True}
        return {}

    # ─── 前递逻辑（Step 4 会用到，先写骨架）───

    def _forward_alu_a(self, rs: int) -> tuple:
        """前递 ALU 输入 A，返回 (值, 是否转发, 源地址, 源段名)"""
        if (self.ex_mem.op and self.ex_mem.reg_write and self.ex_mem.rd is not None
                and self.ex_mem.rd == rs and rs != 0):
            return self.ex_mem.alu_result, True, self.ex_mem.instr_addr, "EX"
        if (self.mem_wb.op and self.mem_wb.reg_write and self.mem_wb.rd is not None
                and self.mem_wb.rd == rs and rs != 0):
            result = self.mem_wb.mem_data if self.mem_wb.mem_to_reg else self.mem_wb.alu_result
            return result, True, self.mem_wb.instr_addr, "MEM"
        if (self._prev_mem_wb_op and self._prev_mem_wb_reg_write and self._prev_mem_wb_rd is not None
                and self._prev_mem_wb_rd == rs and rs != 0):
            result = self._prev_mem_wb_mem_data if self._prev_mem_wb_mem_to_reg else self._prev_mem_wb_alu_result
            return result, True, self._prev_mem_wb_instr_addr, "MEM"
        return self.regfile.read(rs), False, 0, None

    def _forward_alu_b(self, rt: int) -> tuple:
        """前递 ALU 输入 B，返回 (值, 是否转发, 源地址, 源段名)"""
        if (self.ex_mem.op and self.ex_mem.reg_write and self.ex_mem.rd is not None
                and self.ex_mem.rd == rt and rt != 0):
            return self.ex_mem.alu_result, True, self.ex_mem.instr_addr, "EX"
        if (self.mem_wb.op and self.mem_wb.reg_write and self.mem_wb.rd is not None
                and self.mem_wb.rd == rt and rt != 0):
            result = self.mem_wb.mem_data if self.mem_wb.mem_to_reg else self.mem_wb.alu_result
            return result, True, self.mem_wb.instr_addr, "MEM"
        if (self._prev_mem_wb_op and self._prev_mem_wb_reg_write and self._prev_mem_wb_rd is not None
                and self._prev_mem_wb_rd == rt and rt != 0):
            result = self._prev_mem_wb_mem_data if self._prev_mem_wb_mem_to_reg else self._prev_mem_wb_alu_result
            return result, True, self._prev_mem_wb_instr_addr, "MEM"
        return self.regfile.read(rt), False, 0, None

    # ─── 主时钟周期 ──────────────────────────

    def step(self):
        """执行一个时钟周期"""
        self.cycle += 1
        self.stats.total_cycles += 1
        self.events = []
        self._fwd_events = []

        # 保存本周期初 MEM/WB（用于 WB 段显示 + 前递）
        self._prev_mem_wb_op = self.mem_wb.op
        self._prev_mem_wb_instr_addr = self.mem_wb.instr_addr
        self._prev_mem_wb_alu_result = self.mem_wb.alu_result
        self._prev_mem_wb_rd = self.mem_wb.rd
        self._prev_mem_wb_reg_write = self.mem_wb.reg_write
        self._prev_mem_wb_mem_to_reg = self.mem_wb.mem_to_reg
        self._prev_mem_wb_mem_data = self.mem_wb.mem_data

        # 1. WB 段：写回寄存器
        self._step_wb()

        # 2. MEM 段：数据内存访问
        self._step_mem()

        # 3. EX 段：ALU 执行
        self._step_ex()

        # 4. ID 段：译码 + 冒险检测
        self._step_id()

        # 5. IF 段：取指
        self._step_if()

        # 更新指令跟踪
        self._update_tracking()

        # 检查断点
        self._check_breakpoints()

    def _step_wb(self):
        if self.mem_wb.op is None:
            return
        if self.mem_wb.reg_write and self.mem_wb.rd is not None and self.mem_wb.rd != 0:
            value = self.mem_wb.mem_data if self.mem_wb.mem_to_reg else self.mem_wb.alu_result
            self.regfile.write(self.mem_wb.rd, value)
        self.stats.completed_instructions += 1

    def _step_mem(self):
        if self.ex_mem.op is None:
            self.mem_wb.op = None
            return
        if self.ex_mem.mem_read:
            self.mem_wb.mem_data = self.dmem.read(self.ex_mem.alu_result)
        else:
            self.mem_wb.mem_data = 0
        if self.ex_mem.mem_write:
            self.dmem.write(self.ex_mem.alu_result, self.ex_mem.reg_b)

        self.mem_wb.alu_result = self.ex_mem.alu_result
        self.mem_wb.rd = self.ex_mem.rd
        self.mem_wb.op = self.ex_mem.op
        self.mem_wb.instr_addr = self.ex_mem.instr_addr
        self.mem_wb.reg_write = self.ex_mem.reg_write
        self.mem_wb.mem_to_reg = self.ex_mem.mem_to_reg

    def _step_ex(self):
        if self.id_ex.op is None:
            self.ex_mem.clear()
            return

        op = self.id_ex.op
        reg_a_val = self.id_ex.reg_a
        reg_b_val = self.id_ex.reg_b

        if self.forwarding_on:
            if self.id_ex.rs is not None:
                fwd_a, did_fwd_a, src_addr, src_stage = self._forward_alu_a(self.id_ex.rs)
                if did_fwd_a:
                    reg_a_val = fwd_a
                    self.events.append(f"Forward: r{self.id_ex.rs} 从 {src_stage} 转发到 EX")
                    self.stats.forwarding_saved += 1
                    self._fwd_events.append({
                        "cycle": self.cycle, "from_addr": src_addr,
                        "to_addr": self.id_ex.instr_addr, "register": self.id_ex.rs,
                        "src_stage": src_stage,
                    })

            alu_b_src = self.id_ex.rt if not self.id_ex.alu_src else None
            if alu_b_src is not None:
                fwd_b, did_fwd_b, src_addr, src_stage = self._forward_alu_b(alu_b_src)
                if did_fwd_b:
                    reg_b_val = fwd_b
                    self._fwd_events.append({
                        "cycle": self.cycle, "from_addr": src_addr,
                        "to_addr": self.id_ex.instr_addr, "register": alu_b_src,
                        "src_stage": src_stage,
                    })

        # sw 存数 forwarding：从 EX/MEM 或 MEM/WB 转发到存储值
        if op == "sw" and self.forwarding_on and self.id_ex.rt is not None:
            fwd_store, did_fwd_store, src_addr, src_stage = self._forward_alu_b(self.id_ex.rt)
            if did_fwd_store:
                reg_b_val = fwd_store
                self.events.append(f"Forward: r{self.id_ex.rt} 存数值从 {src_stage} 转发到 MEM")
                self._fwd_events.append({
                    "cycle": self.cycle, "from_addr": src_addr,
                    "to_addr": self.id_ex.instr_addr, "register": self.id_ex.rt,
                    "src_stage": src_stage,
                })

        if op == "add":
            alu_result = ALU.add(reg_a_val, reg_b_val)
        elif op in ("lw", "sw", "addi"):
            alu_result = ALU.add(reg_a_val, self.id_ex.imm)
        elif op == "beqz":
            alu_result = reg_a_val
            # 分支判断
            if reg_a_val == 0:
                target = self.id_ex.instr_addr + 4 + self.id_ex.imm
                self.pc.set(target)
                self._flush_id = True
                self.if_id.instruction = None
                self.events.append(f"Branch taken: beqz 跳转到 0x{target:04X}，冲刷 IF/ID")
                self.stats.control_stalls += 2
        else:
            alu_result = 0

        self.ex_mem.alu_result = alu_result
        self.ex_mem.reg_b = reg_b_val
        self.ex_mem.rd = self.id_ex.rd if self.id_ex.reg_dst else self.id_ex.rt
        self.ex_mem.op = op
        self.ex_mem.instr_addr = self.id_ex.instr_addr
        self.ex_mem.reg_write = self.id_ex.reg_write
        self.ex_mem.mem_read = self.id_ex.mem_read
        self.ex_mem.mem_write = self.id_ex.mem_write
        self.ex_mem.mem_to_reg = self.id_ex.mem_to_reg

    def _step_id(self):
        # 处理 EX 段发来的冲刷信号（分支跳转）
        if self._flush_id:
            self.id_ex.op = None
            self._flush_id = False
            self._id_instruction = None
            return

        if self.if_id.instruction is None:
            self.id_ex.op = None
            self._id_instruction = None
            return

        instr = self.if_id.instruction
        op = instr["op"]
        controls = self._gen_controls(instr)

        rs = instr.get("rs", 0) or 0
        rt = instr.get("rt", 0) or 0
        rd = instr.get("rd")

        # ── RAW 冒险检测 ──────────────────────────
        stall_needed = False

        # 检查 EX/MEM 中的目标寄存器
        if self.ex_mem.op and self.ex_mem.reg_write and self.ex_mem.rd is not None and self.ex_mem.rd != 0:
            ex_dst = self.ex_mem.rd
            # Load-Use: 上一条是 lw，当前指令依赖其结果
            if self.ex_mem.mem_read:
                if (op in ("add", "addi", "lw", "sw", "beqz") and rs == ex_dst) or \
                   (op in ("add", "sw", "beqz") and rt == ex_dst):
                    stall_needed = True
                    self.events.append(f"Load-Use stall: {instr['text']} 等待 r{ex_dst} (lw 在 MEM 段)")
                    self.stats.load_use_stalls += 1
            elif not self.forwarding_on:
                # 无转发时，add 的结果要到 WB 才能用
                if (op in ("add", "addi", "lw", "sw", "beqz") and rs == ex_dst) or \
                   (op in ("add", "sw", "beqz") and rt == ex_dst):
                    stall_needed = True
                    self.events.append(f"RAW stall: {instr['text']} 等待 r{ex_dst} (无转发)")
                    self.stats.data_stalls += 1
            # 有转发时 add→add 不需要停顿，但 lw→use 已在上面处理

        # 检查 MEM/WB 中的目标寄存器（无转发时需要等）
        if not stall_needed and not self.forwarding_on:
            if self.mem_wb.op and self.mem_wb.reg_write and self.mem_wb.rd is not None and self.mem_wb.rd != 0:
                mem_dst = self.mem_wb.rd
                if (op in ("add", "addi", "lw", "sw", "beqz") and rs == mem_dst) or \
                   (op in ("add", "sw", "beqz") and rt == mem_dst):
                    stall_needed = True
                    self.events.append(f"RAW stall: {instr['text']} 等待 r{mem_dst} (无转发)")
                    self.stats.data_stalls += 1

        if stall_needed:
            # 插入气泡，保持 IF/ID 不变（PC 不更新）
            self.id_ex.op = None
            self._stall_pc = True
            self._id_instruction = instr  # 指令停在ID段
            return

        # ── 正常译码 ─────────────────────────────────
        self._id_instruction = instr

        reg_a = self.regfile.read(rs) if rs is not None else 0
        reg_b = self.regfile.read(rt) if rt is not None else 0
        imm = instr.get("imm", 0) or 0

        if controls["reg_dst"]:
            dest_reg = rd
        else:
            dest_reg = rt

        self.id_ex.pc_plus_4 = self.if_id.pc_plus_4
        self.id_ex.reg_a = reg_a
        self.id_ex.reg_b = reg_b
        self.id_ex.imm = imm
        self.id_ex.rd = dest_reg
        self.id_ex.rs = rs
        self.id_ex.rt = rt
        self.id_ex.op = op
        self.id_ex.instr_addr = self.if_id.instr_addr
        self.id_ex.reg_write = controls["reg_write"]
        self.id_ex.mem_read = controls["mem_read"]
        self.id_ex.mem_write = controls["mem_write"]
        self.id_ex.alu_src = controls["alu_src"]
        self.id_ex.reg_dst = controls["reg_dst"]
        self.id_ex.mem_to_reg = controls["mem_to_reg"]
        self.id_ex.branch = controls["branch"]

    def _step_if(self):
        if self._stall_pc:
            # PC 不更新，保持当前 if_id 不变（ID 段需要重复译码同一条指令）
            self._stall_pc = False
            return

        current_pc = self.pc.get()
        instr = self.imem.fetch(current_pc)
        if instr is not None:
            self.if_id.pc_plus_4 = current_pc + 4
            self.if_id.instruction = instr
            self.if_id.instr_addr = current_pc
            self.pc.next()
        else:
            self.if_id.instruction = None
            self.if_id.pc_plus_4 = current_pc
            self.if_id.instr_addr = 0

    # ─── 指令跟踪 ────────────────────────────────

    def _update_tracking(self):
        """更新每条指令当前所在的流水段"""
        for addr in self.instr_tracking:
            self.instr_tracking[addr]["stage"] = None

        for i, instr in enumerate(self.instructions):
            addr = i * 4
            stage = self._find_instruction_stage(instr)
            if addr in self.instr_tracking:
                self.instr_tracking[addr]["stage"] = stage

    # ─── 断点检查 ────────────────────────────────

    def _check_breakpoints(self):
        """检查是否命中断点"""
        # PC 断点
        if self.pc.get() in self.pc_breakpoints:
            self.running = False
            self.paused_by = f"pc:0x{self.pc.get():04X}"
            return

        # 段断点：检查当前段是否有有效指令
        stage_map = {
            "IF": self.if_id.instruction is not None,
            "ID": self.id_ex.op is not None,
            "EX": self.ex_mem.op is not None,
            "MEM": self.mem_wb.op is not None,
            "WB": self._prev_mem_wb_op is not None,
        }
        for stage in self.stage_breakpoints:
            if stage_map.get(stage, False):
                self.running = False
                self.paused_by = f"stage:{stage}"
                return

    # ─── 状态快照 ────────────────────────────────

    def get_snapshot(self) -> dict:
        """返回当前完整状态 JSON"""
        return {
            "cycle": self.cycle,
            "pc": self.pc.get(),
            "forwarding_on": self.forwarding_on,
            "running": self.running,
            "paused_by": self.paused_by,
            "breakpoints": {
                "pc": sorted(list(self.pc_breakpoints)),
                "stages": sorted(list(self.stage_breakpoints)),
            },
            "stages": {
                "IF": self._stage_state(self.if_id.instruction),
                "ID": self._stage_state_id(),
                "EX": self._stage_state_ex(),
                "MEM": self._stage_state_mem(),
                "WB": self._stage_state_wb(),
            },
            "pipeline_regs": self._pipeline_regs_snapshot(),
            "registers": self.regfile.dump(),
            "instructions": self._instructions_snapshot(),
            "data_memory": self.dmem.dump(),
            "events": self.events.copy(),
            "forwarding": self._fwd_events.copy(),
            "stats": {
                "total_cycles": self.stats.total_cycles,
                "completed_instructions": self.stats.completed_instructions,
                "cpi": self.stats.cpi,
                "data_stalls": self.stats.data_stalls,
                "load_use_stalls": self.stats.load_use_stalls,
                "control_stalls": self.stats.control_stalls,
                "forwarding_saved": self.stats.forwarding_saved,
            },
        }

    def _instr_text_at(self, addr: int) -> Optional[str]:
        idx = addr // 4
        if 0 <= idx < len(self.instructions):
            return self.instructions[idx]["text"]
        return None

    def _stage_state(self, instr: Optional[dict]) -> dict:
        if instr is None:
            return {"instr": None, "pc": None, "bubble": True}
        return {"instr": instr["text"], "pc": self._instr_addr(instr), "bubble": False}

    def _stage_state_id(self) -> dict:
        if self.id_ex.op is not None:
            text = self._instr_text_at(self.id_ex.instr_addr)
            return {"instr": text or self.id_ex.op, "pc": self.id_ex.instr_addr, "bubble": False}
        # 当 ID/EX 为空但 ID 段有被 stall 的指令时
        if self._id_instruction is not None:
            return {"instr": self._id_instruction["text"], "pc": self.if_id.instr_addr, "bubble": False}
        return {"instr": None, "pc": None, "bubble": True}

    def _stage_state_ex(self) -> dict:
        if self.ex_mem.op is None:
            return {"instr": None, "pc": None, "bubble": True}
        text = self._instr_text_at(self.ex_mem.instr_addr)
        return {"instr": text or self.ex_mem.op, "pc": self.ex_mem.instr_addr, "bubble": False}

    def _stage_state_mem(self) -> dict:
        if self.mem_wb.op is None:
            return {"instr": None, "pc": None, "bubble": True}
        text = self._instr_text_at(self.mem_wb.instr_addr)
        return {"instr": text or self.mem_wb.op, "pc": self.mem_wb.instr_addr, "bubble": False}

    def _stage_state_wb(self) -> dict:
        if self._prev_mem_wb_op is None:
            return {"instr": None, "pc": None, "bubble": True}
        text = self._instr_text_at(self._prev_mem_wb_instr_addr)
        return {"instr": text or self._prev_mem_wb_op, "pc": self._prev_mem_wb_instr_addr, "bubble": False}

    def _instr_addr(self, instr: dict) -> Optional[int]:
        for i, inst in enumerate(self.instructions):
            if inst["text"] == instr["text"]:
                return i * 4
        return None

    def _pipeline_regs_snapshot(self) -> dict:
        return {
            "IF_ID": {
                "pc_plus_4": self.if_id.pc_plus_4,
                "instruction": self.if_id.instruction["text"] if self.if_id.instruction else None,
                "instr_addr": self.if_id.instr_addr,
                "op": self.if_id.instruction["op"] if self.if_id.instruction else None,
            },
            "ID_EX": {
                "pc_plus_4": self.id_ex.pc_plus_4,
                "op": self.id_ex.op,
                "instr_addr": self.id_ex.instr_addr,
                "reg_a": self.id_ex.reg_a,
                "reg_b": self.id_ex.reg_b,
                "imm": self.id_ex.imm,
                "rd": self.id_ex.rd,
                "rs": self.id_ex.rs,
                "rt": self.id_ex.rt,
                "controls": {
                    "reg_write": self.id_ex.reg_write,
                    "mem_read": self.id_ex.mem_read,
                    "mem_write": self.id_ex.mem_write,
                    "alu_src": self.id_ex.alu_src,
                    "reg_dst": self.id_ex.reg_dst,
                    "mem_to_reg": self.id_ex.mem_to_reg,
                    "branch": self.id_ex.branch,
                },
            } if self.id_ex.op else {"pc_plus_4": 0, "op": None, "instr_addr": 0,
                                       "reg_a": 0, "reg_b": 0, "imm": 0,
                                       "rd": None, "rs": None, "rt": None,
                                       "controls": {"reg_write": False, "mem_read": False,
                                                     "mem_write": False, "alu_src": False,
                                                     "reg_dst": False, "mem_to_reg": False,
                                                     "branch": False}},
            "EX_MEM": {
                "op": self.ex_mem.op,
                "instr_addr": self.ex_mem.instr_addr,
                "alu_result": self.ex_mem.alu_result,
                "reg_b": self.ex_mem.reg_b,
                "rd": self.ex_mem.rd,
                "controls": {
                    "reg_write": self.ex_mem.reg_write,
                    "mem_read": self.ex_mem.mem_read,
                    "mem_write": self.ex_mem.mem_write,
                    "mem_to_reg": self.ex_mem.mem_to_reg,
                },
            } if self.ex_mem.op else {"op": None, "instr_addr": 0,
                                       "alu_result": 0, "reg_b": 0, "rd": None,
                                       "controls": {"reg_write": False, "mem_read": False,
                                                     "mem_write": False, "mem_to_reg": False}},
            "MEM_WB": {
                "op": self.mem_wb.op,
                "instr_addr": self.mem_wb.instr_addr,
                "mem_data": self.mem_wb.mem_data,
                "alu_result": self.mem_wb.alu_result,
                "rd": self.mem_wb.rd,
                "controls": {
                    "reg_write": self.mem_wb.reg_write,
                    "mem_to_reg": self.mem_wb.mem_to_reg,
                },
            } if self.mem_wb.op else {"op": None, "instr_addr": 0,
                                       "mem_data": 0, "alu_result": 0, "rd": None,
                                       "controls": {"reg_write": False, "mem_to_reg": False}},
        }

    def _instructions_snapshot(self) -> list[dict]:
        """生成指令列表快照，标注每条指令所在段"""
        result = []
        for i, instr in enumerate(self.instructions):
            addr = i * 4
            track = self.instr_tracking.get(addr, {})
            stage = self._find_instruction_stage(instr)
            result.append({
                "id": i,
                "addr": addr,
                "text": instr["text"],
                "stage": stage,
                "done": track.get("done", False),
                "flushed": track.get("flushed", False),
            })
        return result

    def _find_instruction_stage(self, instr: dict) -> Optional[str]:
        """查找指令当前所在流水段（按地址匹配）"""
        addr = self._instr_addr(instr)
        if addr is None:
            return None
        if self.if_id.instr_addr == addr and self.if_id.instruction is not None:
            return "IF"
        if self.id_ex.op is not None and self.id_ex.instr_addr == addr:
            return "ID"
        if self.ex_mem.op is not None and self.ex_mem.instr_addr == addr:
            return "EX"
        if self.mem_wb.op is not None and self.mem_wb.instr_addr == addr:
            return "MEM"
        if self._prev_mem_wb_op is not None and self._prev_mem_wb_instr_addr == addr:
            return "WB"
        current_pc = self.pc.get()
        if addr < current_pc:
            return "DONE"
        return None

    # ─── 运行控制 ────────────────────────────────

    def run_until_stop(self):
        """连续运行直到程序结束或命中端点"""
        self.running = True
        self.paused_by = None
        while self.running:
            # 检查是否所有指令都完成了
            if self._all_done():
                self.running = False
                self.paused_by = "complete"
                break
            self.step()
            if not self.running:
                break

    def _all_done(self) -> bool:
        """检查是否所有指令都已完成"""
        if not self.instructions:
            return False
        return (self.if_id.instruction is None
                and self.id_ex.op is None
                and self.ex_mem.op is None
                and self.mem_wb.op is None
                and self.pc.get() >= len(self.instructions) * 4)

    def set_pc_breakpoint(self, addr: int):
        self.pc_breakpoints.add(addr)

    def del_pc_breakpoint(self, addr: int):
        self.pc_breakpoints.discard(addr)

    def set_stage_breakpoint(self, stage: str):
        self.stage_breakpoints.add(stage)

    def del_stage_breakpoint(self, stage: str):
        self.stage_breakpoints.discard(stage)

    def toggle_forwarding(self):
        self.forwarding_on = not self.forwarding_on
