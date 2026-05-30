# 上机实验 2：流水线性能分析 — 实验报告

| 项目 | 内容 |
|------|------|
| 姓名 | |
| 学号 | |
| 班级 | |
| 日期 | |

---

## 目录

1. [实验目的](#1-实验目的)
2. [实验平台](#2-实验平台)
3. [模拟器设计思想与特色](#3-模拟器设计思想与特色)
   - 3.1 模拟器 A（自研流水线模拟器）— 逐模块代码分析
   - 3.2 模拟器 B（开源流水线模拟器）
4. [测试代码组合](#4-测试代码组合)
5. [测试代码执行过程与分析](#5-测试代码执行过程与分析)
   - 5.1 场景一：无冲突流水线
   - 5.2 场景二：RAW 数据冲突
   - 5.3 场景三：分支跳转（控制冲突）
6. [性能统计对比](#6-性能统计对比)
7. [实验感悟](#7-实验感悟)

---

## 1. 实验目的

1. 加深对计算机流水线基本概念的理解；
2. 理解 MIPS 结构如何用 5 段流水线来实现，理解各段的功能和基本操作；
3. 加深对数据冲突、结构冲突、控制冲突的理解，并能够分析这些冲突对 CPU 性能的影响；
4. 进一步理解解决数据冲突的方法，掌握如何应用定向（Forwarding）技术来减少数据冲突引起的流水线停顿。

## 2. 实验平台

### 2.1 模拟器 A：自研 MIPS 五段流水线模拟器

| 项目 | 选择 |
|------|------|
| 后端语言 | Python 3 |
| Web 框架 | Flask |
| 前端 | 原生 HTML/CSS/JS（单页应用） |
| 体系结构 | MIPS32（32 位，32 个通用寄存器） |
| 运行方式 | `python app.py` 本地启动，浏览器访问 |

**项目结构：**

```
five_stage_pipeline/
├── app.py            # Flask 入口：API 路由 + 启动服务器
├── pipeline.py       # 流水线核心：5段逻辑 + 段间寄存器 + 冲突处理
├── datapath.py       # 数据通路：寄存器堆、内存、ALU、PC
├── assembler.py      # 汇编器：MIPS 指令文本 → 内部表示
├── templates/
│   └── index.html    # 前端页面：时空图 + 寄存器 + 指令列表 + 统计面板
└── test_programs/
    ├── no_hazard.txt     # 场景1：无冲突
    ├── raw_hazard.txt    # 场景2：RAW冲突
    └── branch.txt        # 场景3：分支跳转
```

**支持的指令集：** `add`, `addi`, `lw`, `sw`, `beqz`

> **注意**：以下"模拟器 A"部分的内容请在运行模拟器后，结合网页截图补充完整。报告中至少需要包含每个场景的**截图**和**分析**。

### 2.2 模拟器 B：开源流水线模拟器

> **说明**：此处填写你选择的开源模拟器（如 SPIM、MARS、WinMIPS64 等）的名称、版本、基本功能描述。

| 项目 | 内容 |
|------|------|
| 模拟器名称 | |
| 版本 | |
| 主要功能 | |
| 运行方式 | |

---

## 3. 模拟器设计思想与特色

### 3.1 模拟器 A（自研模拟器）— 逐模块代码分析

模拟器 A 采用**前后端分离架构**，后端用 Python + Flask 实现完整的 MIPS 五段流水线数据通路和冲突检测逻辑，前端用原生 HTML/CSS/JS 构建可视化仪表盘，两者通过 REST JSON API 通信。

#### 3.1.1 整体架构与数据流

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        数据流全景                                          │
│                                                                          │
│  用户输入 MIPS 汇编代码 (字符串)                                           │
│         │                                                                │
│         ▼                                                                │
│    assemblies / parse_program()     ← 纯函数解析，零副作用                    │
│         │                                                                │
│         ▼                                                                │
│   指令字典列表 → PipelineSimulator.load_program()                          │
│         │                                                                │
│         ▼  每个时钟周期 step() 按逆序推进                                    │
│   WB → MEM → EX → ID → IF → (更新跟踪) → (检查断点)                        │
│         │                                                                │
│         ▼                                                                │
│   get_snapshot() → 完整状态 JSON → HTTP Response → 前端渲染                 │
└──────────────────────────────────────────────────────────────────────────┘
```

**关键设计决策：流水段逆序推进**

`pipeline.py` 第 264-280 行展示了核心 step() 方法：

```python
def step(self):
    self.cycle += 1
    self.stats.total_cycles += 1
    self.events = []
    self._fwd_events = []
    # 保存本周期初 MEM/WB（用于 WB 段显示 + 前递）
    self._prev_mem_wb_op = self.mem_wb.op
    ...
    self._step_wb()    # 1. WB 段：写回寄存器
    self._step_mem()   # 2. MEM 段：数据内存访问
    self._step_ex()    # 3. EX 段：ALU 执行
    self._step_id()    # 4. ID 段：译码 + 冒险检测
    self._step_if()    # 5. IF 段：取指
    self._update_tracking()
    self._check_breakpoints()
```

选择**逆序推进**（从 WB 到 IF），而不是顺序推进（IF→WB），目的是避免**写后读冲突**：如果在写回完成之前，前段就读了寄存器，会读到旧值。逆序保证每个段读入的都是上一周期结束时的最新状态。

> 在真实的硬件实现中，所有段实际上是同时推进的。逆序软件模拟是一种常见的技巧，等价于用"保存上一周期状态 → 全部并行更新 → 复制到当前状态"的方式。

#### 3.1.2 数据通路层（datapath.py）— 硬件组件模型

`datapath.py` 实现了 5 个独立的硬件组件类，每个类对应 MIPS 数据通路中的一个真实部件：

| 类名 | 行号 | 对应硬件 | 核心接口 | 关键实现细节 |
|------|------|----------|---------|-------------|
| `RegisterFile` | 6-22 | 寄存器堆（32×32位） | `read(reg_num)`, `write(reg_num, value)` | `$0` 恒为 0：第 12-14 行判断 `reg_num == 0` 时强制返回 0；第 17-19 行 `write()` 中禁止向 `$0` 写入 |
| `InstructionMemory` | 25-38 | 指令存储器 | `load(instructions)`, `fetch(addr)` | 第 33-35 行按 `addr = i * 4` 存储，模拟按字节寻址；返回 `Optional[dict]` 类型 |
| `DataMemory` | 41-67 | 数据存储器 | `read(addr)`, `write(addr, value)` | 第 48-53 行地址对齐检测 `addr % 4 != 0`；第 66 行 `dump()` 只返回被访问过的地址 |
| `ALU` | 70-79 | 算术逻辑单元 | `add(a, b)`, `sub(a, b)` | 静态方法；第 74 行 `& 0xFFFFFFFF` 截断为 32 位，模拟硬件溢出行为 |
| `PC` | 82-95 | 程序计数器 | `get()`, `set(addr)`, `next()` | 第 91-94 行 `set()` 和 `next()` 都有 `& 0xFFFFFFFF` 地址截断 |

**寄存器堆设计要点（第 6-22 行）：**

```python
class RegisterFile:
    def __init__(self):
        self.regs = [0] * 32        # 32个寄存器，初始全0

    def read(self, reg_num: int) -> int:
        if reg_num == 0:
            return 0                 # $0 硬连线为0，读返回0
        return self.regs[reg_num]

    def write(self, reg_num: int, value: int):
        if reg_num != 0:
            self.regs[reg_num] = value & 0xFFFFFFFF  # $0 禁止写入
```

MIPS 架构规定 `$zero`（`$0`）永远返回 0，任何写入操作对其无效。这里的实现精确模拟了硬件行为。

**数据内存地址对齐检查（第 48-53 行）：**

```python
def _check_addr(self, addr: int):
    if addr % 4 != 0:
        raise ValueError(f"地址 {addr} 未对齐")
    idx = addr // 4
    if idx < 0 or idx >= len(self.mem):
        raise ValueError(f"地址 {addr} 越界")
    return idx
```

MIPS 要求所有内存访问必须按字对齐（地址是 4 的倍数），未对齐访问触发异常。数据内存按字（32 位）存储，内部 `mem` 数组以字为单位，`addr // 4` 将字节地址转换为字索引。

#### 3.1.3 汇编器（assembler.py）— 指令解析

`assembler.py` 的功能是将用户输入的 MIPS 汇编文本解析为模拟器内部使用的指令字典。

**核心函数链：**

```python
# parse_line() 第 31-102 行：单行解析，返回 dict 或 None
# parse_program() 第 105-115 行：多行循环调用 parse_line()
# parse_register() 第 7-18 行：寄存器名 → 数字编号
# parse_offset_imm() 第 21-28 行：立即数字符串 → int
```

**每条指令的内部表示格式（dict）：**

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `op` | str | 操作码 | `"add"`, `"lw"`, `"sw"`, `"addi"`, `"beqz"` |
| `rd` | int 或 None | 目标寄存器号 | `add` 指令目标 |
| `rs` | int 或 None | 源寄存器号 | 第一个源操作数 |
| `rt` | int 或 None | 第二源寄存器号 | `add` 的第二源操作数，或 `lw`/`sw`/`addi` 的目标 |
| `imm` | int 或 None | 立即数或偏移量 | `lw`/`sw` 的地址偏移，`addi` 的立即数，`beqz` 的跳转偏移 |
| `text` | str | 原始指令文本 | 用于显示和日志 |

**以 add 指令的解析为例（第 52-60 行）：**

```python
if op == 'add':
    m = re.match(r'\s*([r\$]\w+)\s*,\s*([r\$]\w+)\s*,\s*([r\$]\w+)\s*$', operands)
    if not m:
        raise ValueError(f"add 指令格式错误: {line}（正确格式: add rd, rs, rt）")
    rd = parse_register(m.group(1))
    rs = parse_register(m.group(2))
    rt = parse_register(m.group(3))
    return {"op": "add", "rd": rd, "rs": rs, "rt": rt, "imm": None, "text": line}
```

三种寄存器命名风格统一支持（第 8-18 行）：`r1`、`$1`、`$zero`/`r0` 四种写法均可识别。正则表达式 `r'[r\$](\d+)'` 捕获数字部分作为寄存器编号。

**beqz 跳转偏移的设计决策（第 92-99 行）：**

```python
elif op == 'beqz':
    m = re.match(r'\s*([r\$]\w+)\s*,\s*([-\w]+)\s*$', operands)
    rs = parse_register(m.group(1))
    imm = parse_offset_imm(m.group(2))
    return {"op": "beqz", "rs": rs, "imm": imm, "rd": None, "rt": None, "text": line}
```

`beqz` 使用**数值偏移**而非符号标签，跳转目标地址计算为 `PC + 4 + imm`。这种设计避免了引入符号表解析的复杂度，使汇编器保持为纯函数工具。学生在测试时需手动计算偏移值。

#### 3.1.4 段间寄存器（pipeline.py 第 8-66 行）

四个段间寄存器类每个都继承自 `PipelineReg`，使用 Python `@dataclass` 定义，字段对应真实硬件的段间锁存器：

```python
@dataclass
class IF_ID(PipelineReg):     # IF/ID 锁存器
    pc_plus_4: int = 0
    instruction: Optional[dict] = None
    instr_addr: int = 0

@dataclass
class ID_EX(PipelineReg):     # ID/EX 锁存器（包含全部控制信号）
    pc_plus_4: int = 0
    reg_a: int = 0             # rs 读出的值
    reg_b: int = 0             # rt 读出的值
    imm: int = 0
    rd: Optional[int] = None
    rs: Optional[int] = None
    rt: Optional[int] = None
    op: Optional[str] = None
    instr_addr: int = 0
    reg_write: bool = False    # ↓ 下方 6 个控制信号
    mem_read: bool = False
    mem_write: bool = False
    alu_src: bool = False
    reg_dst: bool = False
    mem_to_reg: bool = False
    branch: bool = False
```

| 段间寄存器 | 对应硬件锁存器 | 传递路径 | 所含核心数据 |
|-----------|--------------|---------|-------------|
| `IF_ID` | IF/ID 流水线寄存器 | IF → ID | PC+4, 指令 |
| `ID_EX` | ID/EX 流水线寄存器 | ID → EX | 两个操作数值, 立即数, 寄存器号, 6个控制信号 |
| `EX_MEM` | EX/MEM 流水线寄存器 | EX → MEM | ALU结果, 存储数据, 目标寄存器, 4个控制信号 |
| `MEM_WB` | MEM/WB 流水线寄存器 | MEM → WB | 内存读出数据, ALU结果, 目标寄存器, 2个控制信号 |

`clear()` 方法（第 12-14 行）使用 `__dataclass_fields__` 反射将所有字段置为 `None`，用于在流水线中插入"气泡"：

```python
def clear(self):
    for f in self.__dataclass_fields__:
        setattr(self, f, None)
```

#### 3.1.5 控制信号生成（pipeline.py 第 189-212 行）

```python
def _gen_controls(self, instr: dict) -> dict:
    op = instr["op"]
    if op == "add":
        return {"reg_write": True, "mem_read": False, "mem_write": False,
                 "alu_src": False, "reg_dst": True, "mem_to_reg": False,
                 "branch": False}
    elif op == "lw":
        return {"reg_write": True, "mem_read": True, "mem_write": False,
                 "alu_src": True, "reg_dst": False, "mem_to_reg": True,
                 "branch": False}
    ...
```

**各控制信号含义及指令对照表：**

| 控制信号 | 含义 | add | lw | sw | addi | beqz |
|---------|------|-----|----|----|------|------|
| `reg_write` | 写寄存器 | ✓ | ✓ | ✗ | ✓ | ✗ |
| `mem_read` | 读内存 | ✗ | ✓ | ✗ | ✗ | ✗ |
| `mem_write` | 写内存 | ✗ | ✗ | ✓ | ✗ | ✗ |
| `alu_src` | ALU第二操作数来自立即数 | ✗ | ✓ | ✓ | ✓ | ✗ |
| `reg_dst` | 写回目标为 rd（否则为 rt） | ✓ | ✗ | - | ✗ | - |
| `mem_to_reg` | 写回值来自内存（否则来自 ALU） | ✗ | ✓ | - | ✗ | - |
| `branch` | 是否为分支指令 | ✗ | ✗ | ✗ | ✗ | ✓ |

信号组合方式与经典 MIPS 处理器设计完全一致。例如 `lw` 的 6 个信号全部为 True（`reg_write=mem_read=alu_src=mem_to_reg=True`，`reg_dst=False`），因为需要：① ALU 计算基址+偏移 → ② 读内存 → ③ 写回寄存器（目标来自 rt）。

#### 3.1.6 流水段具体实现

##### (1) WB 段（写回，第 285-291 行）

```python
def _step_wb(self):
    if self.mem_wb.op is None:
        return
    if self.mem_wb.reg_write and self.mem_wb.rd is not None and self.mem_wb.rd != 0:
        value = self.mem_wb.mem_data if self.mem_wb.mem_to_reg else self.mem_wb.alu_result
        self.regfile.write(self.mem_wb.rd, value)
    self.stats.completed_instructions += 1
```

- 先判断 `mem_wb.op is None`：如果 MEM/WB 段为空泡，直接返回。
- 写回值的选择由 `mem_to_reg` 信号决定：若为 True（如 `lw`），写回 `mem_data`（内存读出值）；若为 False（如 `add`/`addi`），写回 `alu_result`（ALU 计算结果）。
- 每条指令完成 WB 段时，`completed_instructions` 计数 +1。

##### (2) MEM 段（访存，第 293-309 行）

```python
def _step_mem(self):
    if self.ex_mem.op is None:
        self.mem_wb.op = None    # 向前传递气泡
        return
    if self.ex_mem.mem_read:
        self.mem_wb.mem_data = self.dmem.read(self.ex_mem.alu_result)
    if self.ex_mem.mem_write:
        self.dmem.write(self.ex_mem.alu_result, self.ex_mem.reg_b)
    # 将 EX/MEM 段间寄存器的值拷贝到 MEM/WB
    self.mem_wb.alu_result = self.ex_mem.alu_result
    self.mem_wb.rd = self.ex_mem.rd
    ...
```

- 为 `lw` 提供读内存操作（地址来自 ALU 计算结果），为 `sw` 提供写内存操作（写的数据来自 EX/MEM 中的 `reg_b`，即 rt 寄存器的值）。
- 此段将 `EX/MEM` 中的值同步复制到 `MEM/WB` 中，模拟段间锁存器的数据传递。

##### (3) EX 段（执行，第 311-381 行）

这是五段中最复杂的逻辑段，包含：ALU 运算、Forwarding 转发、分支判断。

```python
def _step_ex(self):
    if self.id_ex.op is None:
        self.ex_mem.clear()
        return
    op = self.id_ex.op
    reg_a_val = self.id_ex.reg_a
    reg_b_val = self.id_ex.reg_b

    if self.forwarding_on:
        # A 端口转发
        if self.id_ex.rs is not None:
            fwd_a, did_fwd_a, src_addr, src_stage = self._forward_alu_a(self.id_ex.rs)
            if did_fwd_a:
                reg_a_val = fwd_a
                ...
        # B 端口转发（仅当 alu_src=False 时）
        alu_b_src = self.id_ex.rt if not self.id_ex.alu_src else None
        if alu_b_src is not None:
            fwd_b, did_fwd_b, src_addr, src_stage = self._forward_alu_b(alu_b_src)
            ...
        # sw 存数转发
        if op == "sw" and ...:
            fwd_store, did_fwd_store, ... = self._forward_alu_b(self.id_ex.rt)
            ...

    # ALU 运算
    if op == "add":
        alu_result = ALU.add(reg_a_val, reg_b_val)
    elif op in ("lw", "sw", "addi"):
        alu_result = ALU.add(reg_a_val, self.id_ex.imm)
    elif op == "beqz":
        alu_result = reg_a_val
        if reg_a_val == 0:
            target = self.id_ex.instr_addr + 4 + self.id_ex.imm
            self.pc.set(target)
            self._flush_id = True
            self.if_id.instruction = None
            ...
```

**ALU 运算规则：** `add` 类型使用两个寄存器值；`lw`/`sw`/`addi` 使用寄存器值 + 立即数（`alu_src=True` 控制多路选择器）；`beqz` 只判断 rs 的值是否为 0。

**分支判断：** `beqz` 检测到条件成立（`reg_a_val == 0`）时：① PC 设置为跳转目标地址 `instr_addr + 4 + imm`；② 设置 `_flush_id = True`；③ 清空 `if_id.instruction`。`_flush_id` 标志会在 ID 段被检查并清空 ID/EX 寄存器。

##### (4) ID 段（译码 + 冒险检测，第 383-470 行）

ID 段同时完成两件关键工作：指令译码和 RAW 冒险检测。这是流水线中**理解难度最大、也是最核心的代码段**。

**冒险检测的完整逻辑（第 404-441 行，逐行注解版）：**

```python
# ── 1) 检查 EX/MEM 段的指令是否与当前 ID 段指令有 RAW 依赖 ──
if self.ex_mem.op \                          # EX/MEM 段有有效指令
   and self.ex_mem.reg_write \               # 该指令会写寄存器（排除 sw、beqz）
   and self.ex_mem.rd is not None \           # 有目标寄存器
   and self.ex_mem.rd != 0:                   # 且目标不是 $zero
    ex_dst = self.ex_mem.rd

    # ── 1a) Load-Use 检测 ──
    # 条件：EX/MEM 段的指令是 lw（mem_read=True），且 ID 段指令的 rs 或 rt 命中 ex_dst
    if self.ex_mem.mem_read:
        # 检查 rs 是否匹配（所有指令都用 rs）
        if (op in ("add", "addi", "lw", "sw", "beqz") and rs == ex_dst) \
        or (op in ("add", "sw", "beqz") and rt == ex_dst):
            stall_needed = True
            self.events.append(
                f"Load-Use stall: {instr['text']} 等待 r{ex_dst} (lw 在 MEM 段)")
            self.stats.load_use_stalls += 1

    # ── 1b) 一般 RAW 检测（仅在无转发时触发）──
    # 条件：EX/MEM 段指令不是 lw，且没有开启 forwarding
    elif not self.forwarding_on:
        if (op in ("add", "addi", "lw", "sw", "beqz") and rs == ex_dst) \
        or (op in ("add", "sw", "beqz") and rt == ex_dst):
            stall_needed = True
            self.events.append(
                f"RAW stall: {instr['text']} 等待 r{ex_dst} (无转发)")
            self.stats.data_stalls += 1

    # 注意：开启 forwarding 且不是 Load-Use 时，不进入以上任何分支
    # → stall_needed 保持为 False → 正常推进 → 由 EX 段转发解决

# ── 2) 仅无转发时，检查 MEM/WB 段的指令是否与当前 ID 段指令有 RAW 依赖 ──
if not stall_needed and not self.forwarding_on:
    if self.mem_wb.op and self.mem_wb.reg_write \
       and self.mem_wb.rd is not None and self.mem_wb.rd != 0:
        mem_dst = self.mem_wb.rd
        if (op in ("add", "addi", "lw", "sw", "beqz") and rs == mem_dst) \
        or (op in ("add", "sw", "beqz") and rt == mem_dst):
            stall_needed = True
            self.events.append(
                f"RAW stall: {instr['text']} 等待 r{mem_dst} (无转发)")
            self.stats.data_stalls += 1
```

**冒险检测与 Forwarding 的交互（决策树详解）：**

```
                         ID 段开始译码指令 I
                               │
                               ▼
                 ┌─────────────────────────────┐
                 │ 检查 EX/MEM.rd == I.rs/rt ? │
                 └─────────────┬───────────────┘
                               │
                    ┌──────────┴──────────┐
                    ▼                     ▼
                匹配成功              不匹配
                    │                     │
                    ▼                     ▼
        ┌─────────────────────┐    ┌──────────────────────────┐
        │ ex_mem.mem_read ?   │    │ 检查 MEM/WB.rd == I.rs/rt│
        └─────────┬───────────┘    └────────────┬─────────────┘
             是   │   否                         │
          ┌───────▼─────┐              ┌────────┴────────┐
          │ Load-Use    │              │ 匹配成功         │ 不匹配
          │ 必停顿 1 周  │     ┌────────┴────────┐        │
          │ (第408行)   │     │ forwarding_on?  │        │
          └───────┬─────┘     └────────┬────────┘        │
                  │              是    │   否            │
                  ▼               ┌────▼───┐            ▼
            插入气泡               │ 正常    │       正常推进
            ID/EX.op = None       │ 推进    │       (无冲突)
            _stall_pc = True      │ (转发   │
                                  │ 解决)   │
                                  └────────┘
                                       │
                                    EX 段 _step_ex()
                                    调用 _forward_alu_a/b()
                                    覆盖 reg_a_val / reg_b_val
```

**三个关键设计决策：**

1. **为什么先检查 EX/MEM 再检查 MEM/WB？**：流水线中 EX/MEM 段的指令比 MEM/WB 段的指令更新、更接近当前指令。如果先检查 MEM/WB 可能错过依赖更紧的 EX/MEM 段指令。这也对应 Forwarding 的优先级 1 > 优先级 2 的顺序。

2. **为什么 `forwarding_on = True` 时不检查 MEM/WB？**：当转发开启时，MEM/WB 段的数据依然可以通过优先级 2 转发到 ALU 输入。所以在 ID 段无需为 MEM/WB 的依赖插入停顿——这完全由转发路径处理。唯一例外是 Load-Use（`mem_read = True`），因为 lw 的数据在 MEM 段才可用，比 EX 段晚了一个完整周期。

3. **为什么 2 步检查（EX/MEM → MEM/WB）使用相同代码，但分开写？**：分开是因为 EX/MEM 检查需要区分 Load-Use 与普通 RAW（`mem_read` 检查），而 MEM/WB 检查不需要（数据已在 MEM/WB 中）。

**停顿实现的硬件等价（第 436-441 行）：**

```python
if stall_needed:
    self.id_ex.op = None       # 相当于硬件中断 ID/EX 锁存器的写使能
    self._stall_pc = True      # 相当于硬件中 PC 的门控时钟
    self._id_instruction = instr  # 保留当前指令用于界面显示
    return
```

停顿的核心机制：将 ID/EX 段间寄存器的 `op` 设为 `None`（清空该段，等价于插入气泡），同时设置 `_stall_pc = True` 阻止 IF 段前进。这使得下一条本该进入 IF 段的指令"停住"，而正在等待的指令继续在 ID 段不前进到 EX。

在真实硬件中，停顿通过**门控时钟**或**寄存器清零信号**实现：暂停 PC 的时钟使能（不让 IF 段取新指令），将 ID/EX 锁存器清零（插入气泡）。需要停顿的指令（在 ID 段等待的指令）重复从 IF/ID 锁存器中读取，不做新译码。

**正常译码（第 443-470 行）：**

当 `stall_needed == False` 时，流水线正常推进，ID 段完成译码：

```python
# 读取寄存器值（ID 段常规操作）
reg_a = self.regfile.read(rs) if rs is not None else 0
reg_b = self.regfile.read(rt) if rt is not None else 0
imm = instr.get("imm", 0) or 0

# 由 reg_dst 信号选择目标寄存器号
if controls["reg_dst"]:
    dest_reg = rd    # 如 add 指令：目标为 rd
else:
    dest_reg = rt    # 如 lw/addi 指令：目标为 rt

# 将全部译码结果打包写入 ID/EX 段间寄存器
self.id_ex.reg_a = reg_a
self.id_ex.reg_b = reg_b
self.id_ex.imm = imm
self.id_ex.rd = dest_reg
self.id_ex.rs = rs
self.id_ex.rt = rt
self.id_ex.op = op
self.id_ex.instr_addr = self.if_id.instr_addr
# 6 个控制信号
self.id_ex.reg_write = controls["reg_write"]
self.id_ex.mem_read = controls["mem_read"]
...
```

这里虽然是正常译码，但 `reg_a` 和 `reg_b` 读出的值可能并非最终 ALU 的输入值——它们只是"初始值"。如果开启 Forwarding，EX 段的 `_forward_alu_a/b()` 会覆盖这些值。这种**先读后覆盖**的设计，体现了流水线中"预取"和"修正"的硬件思维。

**完整的 Forwarding 交互时序示例（开启 FWD）：**

以 `add r1,r2,r3` → `add r4,r1,r5` 为例：

```
周期 3: add r1 进入 EX，add r4 进入 ID
  EX 段: ALU.add(r2, r3) → alu_result = X  ← 正在计算中
  ID 段: add r4 译码 → reg_a = regfile.read(1) → ???（旧值）
         ID/EX ← reg_a 暂存"可能错误"的值

周期 4: add r1 进入 MEM，add r4 进入 EX
  EX 段: _forward_alu_a(rs=1) → ex_mem.rd == 1 → 命中！
         reg_a_val 被覆盖为 ex_mem.alu_result（即刚算好的 r1）
         ALU.add(转发值, r5) → 正确的 r4 计算结果
```

这个交错时序说明：**ID 段读到的寄存器值可能是过时的，但没关系——EX 段的转发逻辑会在同一周期内用转发值覆盖**。这正是 Forwarding 的精髓：不依赖正确的寄存器值，而是从流水线中截取最新的计算结果。

##### (5) IF 段（取指，第 472-488 行）

```python
def _step_if(self):
    if self._stall_pc:
        self._stall_pc = False
        return                    # PC 不更新，if_id 保持当前指令

    current_pc = self.pc.get()
    instr = self.imem.fetch(current_pc)
    if instr is not None:
        self.if_id.pc_plus_4 = current_pc + 4
        self.if_id.instruction = instr
        self.if_id.instr_addr = current_pc
        self.pc.next()
    else:
        self.if_id.instruction = None    # 无指令时向前传播空泡
```

IF 段从指令内存按当前 PC 取指，存入 IF/ID 段间寄存器。当 `_stall_pc = True` 时，PC 保持不变且 IF/ID 内容也不变，ID 段将在下一周期继续译码同一条指令。硬件中可用门控时钟实现相同的效果。

#### 3.1.7 Forwarding 转发技术详解（pipeline.py 第 216-354 行）

##### 3.1.7.1 为什么需要 Forwarding？

MIPS 五段流水线中，一条指令的运算结果在 **EX 段末尾**（对 `add`）或 **MEM 段末尾**（对 `lw`）才产生，而下一条指令在 **ID 段**就要读取寄存器值作为 ALU 输入。如果下一条指令依赖上一条的结果，没有转发机制就必须停顿，等待结果写回寄存器堆后再读——这在经典五段流水线中需要 2 个额外的周期停顿。

**Forwarding（定向/旁路）的核心思想**：不等到结果写回寄存器，而是将流水线中刚计算出的结果从 EX/MEM 或 MEM/WB 段间寄存器直接"抄近路"送到 ALU 的输入端口。这样 ALU 在同一周期内就能用上刚刚算好的值。

```
无转发的情况：
                CC1     CC2     CC3     CC4     CC5     CC6
add r1,r2,r3:   IF      ID      EX      MEM     WB
                                           └──→ regs[1] = result
add r4,r1,r5:           IF      ID     [STALL] [STALL]  EX
                                         ↑ 等 WB 写回 → 从 regfile 读

有转发的情况：
                CC1     CC2     CC3     CC4     CC5
add r1,r2,r3:   IF      ID      EX      MEM     WB
                                   └──→ 结果直接送到 ALU（同一周期）
add r4,r1,r5:           IF      ID      EX      MEM
                                       ↑ ALU 直接使用转发来的值
```

##### 3.1.7.2 转发通路硬件架构

Forwarding 在物理上对应两条旁路路径，分别从 EX/MEM 段和 MEM/WB 段引出连线回到 ALU 输入端的**多路选择器**（MUX）：

```
                           EX/MEM                   MEM/WB
                    ┌─────────────────┐    ┌──────────────────┐
                    │ alu_result = X  │    │ alu_result = Y   │
                    │                 │    │ mem_data = Z     │
                    └────────┬────────┘    └────────┬─────────┘
                             │                      │
         ID/EX ───────┐     ▼                      ▼
         reg_a = ? ───┤    ┌───────────────────────────┐
                      │    │  ALU 输入 A 转发 MUX       │ ← 由 _forward_alu_a() 控制
                      └───→│  (选择: regs[rs]/EX_MEM/MEM_WB) │
         ID/EX ───────┐   └───────────────────────────┘
         reg_b = ? ───┤    ┌───────────────────────────┐
                      │    │  ALU 输入 B 转发 MUX       │ ← 由 _forward_alu_b() 控制
                      └───→│  (选择: regs[rt]/EX_MEM/MEM_WB/imm) │
                           └───────────────────────────┘
                                     │
                                     ▼
                                   ALU
```

**两条转发路径：**

| 路径 | 源段 | 目标 | 对应函数 | 数据延迟 |
|------|------|------|---------|---------|
| **EX/MEM → EX**（绿色路径） | EX/MEM 段间寄存器 | ALU 输入多路选择器 | `_forward_alu_a/b` 优先级 1 | 0 周期（同一周期可用） |
| **MEM/WB → EX**（紫色路径） | MEM/WB 段间寄存器 | ALU 输入多路选择器 | `_forward_alu_a/b` 优先级 2 | 0 周期（但数据可能来自先前的 EX 段） |

两个 MUX 的选择信号由 `_forward_alu_a()` 和 `_forward_alu_b()` 的返回值决定——当转发命中时，MUX 切换到转发数据线，否则使用默认的寄存器堆输出。

##### 3.1.7.3 转发通路的具体实现（pipeline.py 第 216-244 行）

项目设计了两个对称的转发函数，分别对应 ALU 的两个输入端口 A 和 B：

**`_forward_alu_a(rs)` — A 端口转发（第 216-229 行）：**

```python
def _forward_alu_a(self, rs: int) -> tuple:
    """返回 (转发值, 是否命中, 源指令地址, 源段名)"""

    # [优先级 1] EX/MEM → ALU 输入 A
    # 条件：EX/MEM 段含有有效指令，且该指令写寄存器，且目标寄存器正是当前 ALU 需要的 rs
    if (self.ex_mem.op and self.ex_mem.reg_write and self.ex_mem.rd is not None
            and self.ex_mem.rd == rs and rs != 0):
        self.stats.forwarding_saved += 1
        return self.ex_mem.alu_result, True, self.ex_mem.instr_addr, "EX"

    # [优先级 2] MEM/WB → ALU 输入 A
    # 注意：如果 mem_to_reg 为 True（即 lw 指令），转发的是内存数据而非 ALU 结果
    if (self.mem_wb.op and self.mem_wb.reg_write and self.mem_wb.rd is not None
            and self.mem_wb.rd == rs and rs != 0):
        result = self.mem_wb.mem_data if self.mem_wb.mem_to_reg else self.mem_wb.alu_result
        self.stats.forwarding_saved += 1
        return result, True, self.mem_wb.instr_addr, "MEM"

    # [优先级 3] 上周期的 MEM/WB（本周期已写回，但维护了副本）
    if (self._prev_mem_wb_op and self._prev_mem_wb_reg_write
            and self._prev_mem_wb_rd is not None
            and self._prev_mem_wb_rd == rs and rs != 0):
        result = (self._prev_mem_wb_mem_data
                  if self._prev_mem_wb_mem_to_reg
                  else self._prev_mem_wb_alu_result)
        return result, True, self._prev_mem_wb_instr_addr, "MEM"

    # 都不命中 → 从寄存器堆读取
    return self.regfile.read(rs), False, 0, None
```

**`_forward_alu_b(rt)` — B 端口转发（第 231-244 行）：**

`_forward_alu_b` 的逻辑与 A 端口完全对称，区别在于它匹配的是 B 端口的源寄存器 `rt`。B 端口用于：
- `add` 指令的第二个源操作数（`rt`）
- `sw` 指令要写入内存的数据（`rt` 的值）
- `beqz` 不涉及 B 端口（只检查 `rs`）

**关键实现细节：**

1. **三级优先级的含义**：
   - **优先级 1（EX/MEM → EX）**：流水线中最近一条被执行的指令结果，位于 EX/MEM 段间寄存器中，是最新鲜的值
   - **优先级 2（MEM/WB → EX）**：再早一条指令的结果，可能在 MEM/WB 段
   - **优先级 3（上一周期 MEM/WB 副本）**：最新已通过 WB 段写回的值（从寄存器读等价）
   - 三级设计确保了 `add → add → add` 链式依赖场景中，每条后续指令都能从正确的前一条拿到值

2. **数据来源的多样性**：转发值不一定来自 ALU 结果。`lw` 指令的最终结果在内存中，所以当 MEM/WB 段包含 `lw` 时（`mem_to_reg == True`），转发的值不是 `alu_result` 而是 `mem_data`——这正是第 222 行 `result = self.mem_wb.mem_data if self.mem_wb.mem_to_reg else self.mem_wb.alu_result` 的作用。

3. **`forwarding_saved` 计数器与性能统计**：每次转发成功，`self.stats.forwarding_saved += 1`，记录了因转发而**避免的停顿周期数**。在性能统计面板中，这个数字和实际停顿数据一起显示，帮助学生量化 Forwarding 的优化效果。

4. **`$0` 的排除**：三个优先级都检查了 `rs != 0`。这是因为 `$zero` 恒为 0，即使其他指令错误地向它写入值也不应被转发。

##### 3.1.7.4 EX 段中的转发调用流程（第 316-354 行）

转发逻辑在 `_step_ex()` 方法中实际发生，分为两个步骤：

```python
def _step_ex(self):
    ...
    op = self.id_ex.op
    reg_a_val = self.id_ex.reg_a    # 从 ID/EX 段间寄存器读出的原始值
    reg_b_val = self.id_ex.reg_b

    if self.forwarding_on:
        # ── 步骤 1：ALU 输入 A 的转发 ──
        if self.id_ex.rs is not None:
            fwd_a, did_fwd_a, src_addr, src_stage = self._forward_alu_a(self.id_ex.rs)
            if did_fwd_a:
                reg_a_val = fwd_a        # 覆盖 ID 段读出的值
                self.events.append(f"Forward: r{self.id_ex.rs} 从 {src_stage} 转发到 EX")
                self.stats.forwarding_saved += 1
                self._fwd_events.append({
                    "cycle": self.cycle, "from_addr": src_addr,
                    "to_addr": self.id_ex.instr_addr, "register": self.id_ex.rs,
                    "src_stage": src_stage,
                })

        # ── 步骤 2：ALU 输入 B 的转发 ──
        # 仅当 alu_src=False（来自寄存器）时才需要转发 B 端口
        alu_b_src = self.id_ex.rt if not self.id_ex.alu_src else None
        if alu_b_src is not None:
            fwd_b, did_fwd_b, src_addr, src_stage = self._forward_alu_b(alu_b_src)
            if did_fwd_b:
                reg_b_val = fwd_b
                ...  # 记录事件

        # ── 步骤 3：sw 存数转发（特殊） ──
        # sw 的存储数据虽然经过 ALU（alu_src=True 时 ALU 不涉及 B 端口），
        # 但写入内存的数据仍需要转发
        if op == "sw" and self.forwarding_on and self.id_ex.rt is not None:
            fwd_store, did_fwd_store, src_addr, src_stage = self._forward_alu_b(self.id_ex.rt)
            if did_fwd_store:
                reg_b_val = fwd_store
                ...
```

**`alu_src` 信号对转发的影响**：

| alu_src 值 | 含义 | ALU 输入 B 来源 | 是否需要对 B 端口转发？ |
|-----------|------|----------------|---------------------|
| False | 来自寄存器（`add`, `beqz`） | ID/EX 的 reg_b（rt 值） | √ 需要转发 |
| True | 来自立即数（`lw`, `sw`, `addi`） | ID/EX 的 imm（立即数） | × 不需要（B 端口直接用 imm，转发也没意义） |

这就是第 324 行 `alu_b_src = self.id_ex.rt if not self.id_ex.alu_src else None` 的逻辑：当 `alu_src = True` 时，B 端口使用立即数（而非寄存器值），所以直接设为 `None` 跳过 B 端口转发。

##### 3.1.7.5 转发事件追踪（`_fwd_events`，第 128-130 行）

为了前台时空图能画出**转发路径箭头**，项目在每次转发发生时记录事件详情：

```python
self._fwd_events.append({
    "cycle": self.cycle,           # 当前周期号
    "from_addr": src_addr,         # 转发源指令的地址
    "to_addr": self.id_ex.instr_addr,  # 接收转发指令的地址
    "register": self.id_ex.rs,      # 被转发的寄存器编号
    "src_stage": src_stage,         # 转发来源段名（"EX" 或 "MEM"）
})
```

这些事件在前端渲染为从转发源指令所在行指向目的指令行的箭头。前端可以据此在第 5 列、第 6 列（代表 EX 段和 MEM 段的列）之间画蓝色/紫色线条。

##### 3.1.7.6 无转发时的"保底"机制

当 `forwarding_on = False` 时，转发函数 `_forward_alu_a/b` 仍然可被调用，但 `_step_ex()` 不再主动调它们（第 320 行 `if self.forwarding_on:` 不进入）。此时 ALU 直接使用 ID 段从寄存器堆读出的 `reg_a_val` 和 `reg_b_val`。

同时，ID 段在没有转发时会检测到 RAW 依赖（第 417-423 行、第 427-433 行），插入 2 个或更多周期的停顿，等待 WB 段写入后再读。

##### 3.1.7.7 转发与停顿的配合策略总结

| 场景 | Forwarding ON | Forwarding OFF | 原因 |
|------|:------------:|:-------------:|------|
| `add r1,...` → `add r2,r1,...` | 0 停顿（转发解决） | 2 周期停顿 | `add` 的结果在 EX 段末尾可用，转发走 EX/MEM → EX 路径 |
| `addi r1,...` → `add r2,r1,...` | 0 停顿（转发解决） | 2 周期停顿 | 同上（addi 也是 EX 段出结果） |
| `lw r1,...` → `add r2,r1,...` | 1 周期停顿（Load-Use） | 3 周期停顿 | lw 结果在 MEM 段才可用，即使转发也要等 1 周期 |
| `add r1,**` → `sw **, r1` | 0 停顿（存数转发） | 2 周期停顿 | sw 的写入数据来源于 rt，可以通过 EX/MEM → MEM 转发 |
| `add` → `beqz` | 0 停顿 | 0 停顿 | beqz 在 EX 段才用 rs，add 的 EX 段结果可直接用 |
| 链式 `add→add→add` | 每步转发 0 停顿 | 每步 2 停顿 | 三级优先级保证链式转发的正确性 |

#### 3.1.8 状态快照与视图层（pipeline.py 第 529-672 行）

`get_snapshot()`（第 529-562 行）将整个模拟器状态序列化为 JSON 字典，包含以下部分：

```
┌───────────────────────────────────────────────────────────┐
│  SimulationSnapshot JSON 结构                              │
├───────────────────────────────────────────────────────────┤
│  ├─ cycle, pc, forwarding_on, running, paused_by          │
│  ├─ breakpoints: { pc: [...], stages: [...] }             │
│  ├─ stages: { IF, ID, EX, MEM, WB → { instr, pc, bubble }}│
│  ├─ pipeline_regs: { IF_ID, ID_EX, EX_MEM, MEM_WB }      │
│  ├─ registers: { 0~31 → 十六进制值 }                       │
│  ├─ instructions: [{ addr, text, stage, done, flushed }]  │
│  ├─ data_memory: { addr → value } (仅被访问过的地址)       │
│  ├─ events: [...string...]                                │
│  ├─ forwarding: [{ cycle, from_addr, to_addr, register }] │
│  └─ stats: { total_cycles, completed_instructions, cpi,   │
│               data_stalls, load_use_stalls,               │
│               control_stalls, forwarding_saved }           │
└───────────────────────────────────────────────────────────┘
```

**指令所在段的查找策略（第 691-709 行）：**

```python
def _find_instruction_stage(self, instr: dict) -> Optional[str]:
    addr = self._instr_addr(instr)
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
    if addr < current_pc:
        return "DONE"               # 地址已小于当前 PC → 已完成
```

通过比较指令地址与各段间寄存器 `instr_addr` 字段来判断指令当前所在的流水段，实现了"时空图"的核心逻辑。

#### 3.1.9 断点机制（pipeline.py 第 505-525 行）

支持两种断点类型：

- **PC 地址断点**（第 508-510 行）：每周期 `step()` 结束时检查当前 PC 值是否等于任一已设断点的地址。
- **段断点**（第 513-525 行）：检查 IF/ID/EX/MEM/WB 五段中是否有有效指令的段与已设断点匹配。段断点特别适合调试特定流水段的行为（如观察 `beqz` 刚进入 EX 段时的状态）。

```python
stage_map = {
    "IF": self.if_id.instruction is not None,
    "ID": self.id_ex.op is not None,
    "EX": self.ex_mem.op is not None,
    "MEM": self.mem_wb.op is not None,
    "WB": self._prev_mem_wb_op is not None,
}
```

#### 3.1.10 性能统计（pipeline.py 第 77-89 行）

```python
@dataclass
class PerformanceStats:
    total_cycles: int = 0            # 总时钟周期数
    completed_instructions: int = 0   # 完成指令数（WB段退出）
    data_stalls: int = 0             # 数据停顿（无转发时 add→add）
    load_use_stalls: int = 0         # Load-Use 停顿（lw→add，即使转发也停顿）
    control_stalls: int = 0          # 控制停顿（beqz 跳转冲刷）
    forwarding_saved: int = 0        # 转发避免的停顿次数

    @property
    def cpi(self) -> float:          # CPI = 总周期数 / 完成指令数
        if self.completed_instructions == 0:
            return 0.0
        return round(self.total_cycles / self.completed_instructions, 2)
```

CPI（Cycle Per Instruction）是衡量流水线效率的核心指标。理想流水线中 CPI 趋近于 1.0，而各种冲突会导致 CPI 上升。

#### 3.1.11 Flask API 层（app.py）

`app.py` 将 `PipelineSimulator` 封装为 REST API：

```python
sim = PipelineSimulator()          # 模块级单例

@app.route('/api/step', methods=['POST'])
def api_step():
    sim.step()                      # 执行一个周期
    return jsonify(sim.get_snapshot())  # 返回完整状态 JSON
```

**API 路由一览：**

| 方法 | 路径 | 功能 | 内部调用 |
|------|------|------|---------|
| GET | `/api/state` | 获取状态 | `sim.get_snapshot()` |
| POST | `/api/step` | 单步执行 | `sim.step()` |
| POST | `/api/run` | 连续执行到结束/断点 | `sim.step()` 循环 |
| POST | `/api/pause` | 暂停 | `sim.running = False` |
| POST | `/api/reset` | 重置（保留程序） | `sim.reset()` + `sim.load_program()` |
| POST | `/api/load` | 载入程序 | `parse_program()` → `sim.load_program()` |
| POST | `/api/forwarding` | 切换转发 | `sim.toggle_forwarding()` |
| POST | `/api/breakpoint/set\|del` | 设置/删除断点 | `sim.set_pc_breakpoint()` 等 |
| GET | `/api/files` | 预设文件列表 | `os.listdir('test_programs/')` |
| GET | `/api/stats` | 仅性能统计 | `sim.get_snapshot()['stats']` |

每个 API 返回值都包含完整的状态快照，前端可以直接用 `get_snapshot()` 的结果更新所有面板，无需额外的数据转换。

#### 3.1.12 主要特色总结

1. **五段流水线完整实现**：IF（取指）/ ID（译码）/ EX（执行）/ MEM（访存）/ WB（写回）五段，含完整段间寄存器（IF/ID、ID/EX、EX/MEM、MEM/WB）和控制信号。
2. **Forwarding 定向路径**：可开关切换，开启时 ALU 输入可从 EX/MEM 或 MEM/WB 转发，消除 `add → add` 类型 RAW 冲突的停顿。
3. **Load-Use 检测**：`lw` 指令后依赖其结果的指令即使开启转发也需停顿 1 周期。
4. **分支预测策略**：Predict Not Taken（假设不跳转），跳转时冲刷 IF/ID 段插入 2 个气泡。
5. **可视化仪表盘**：4 面板布局（流水线图、寄存器堆、指令列表、数据内存），可交互操控。
6. **性能统计**：总周期数、CPI、各类停顿次数、转发避免次数。
7. **段间寄存器详情**：每周期展示 4 个段间寄存器的完整内部值。

### 3.2 模拟器 B（开源模拟器）

> 此处描述你选择的开源模拟器的设计思想和特色功能。

---

## 4. 测试代码组合

根据实验要求，设计以下 3 种场景的测试代码：

### 场景 1：无冲突流水线（`no_hazard.txt`）

```asm
# 所有指令无数据依赖，流水线可满载运行
addi r1, r0, 10      # r1 = 10
addi r2, r0, 20      # r2 = 20
addi r3, r0, 30      # r3 = 30
add   r10, r1, r2    # r10 = r1 + r2 = 30
```

**特点**：相邻指令之间无寄存器依赖，流水线无需停顿，CPI 应接近 1.0。

### 场景 2：RAW 数据冲突（`raw_hazard.txt`）

```asm
# 2a. add → add（forwarding 可消除停顿）
addi r2, r0, 0       # r2 = 0
addi r3, r0, 10      # r3 = 10
add   r1, r2, r3     # r1 = r2 + r3 = 10
add   r4, r1, r5     # r4 = r1 + r5, 依赖上一条的 r1

# 2b. lw → add（Load-Use，即使转发也需停顿 1 周期）
lw    r1, 0(r2)      # r1 = MEM[0]
add   r3, r1, r4     # r3 = r1 + r4, 依赖 lw 的 r1
```

**特点**：
- `add → add`：转发开启时无停顿，关闭时需停顿等待 WB 写回。
- `lw → add`（Load-Use）：lw 结果在 MEM 段才可用，即使开启转发也需停顿 1 周期。

### 场景 3：分支跳转（`branch.txt`）

```asm
# beqz 跳转 vs. 不跳转
addi r1, r0, 0       # r1 = 0 → beqz 条件成立
beqz r1, 8           # r1 == 0, 跳转到 PC+4+8
add  r2, r3, r4      # （被冲刷，不执行）
add  r5, r6, r7      # （被冲刷，不执行）
add  r8, r9, r10     # 跳转目标
```

**特点**：采用 Predict Not Taken 策略，跳转时 PC 更新并冲刷 IF/ID 段（插入 2 个气泡浪费的周期）。不跳转时无开销。

---

## 5. 测试代码执行过程与分析

### 5.1 场景一：无冲突流水线

#### 5.1.1 模拟器 A 执行过程

> **[此处粘贴模拟器 A 的网页截图，展示执行完成后的状态]**
>
> - 截图至少包含：流水线时空图、寄存器堆、指令列表、统计面板

**执行分析：**

- **总周期数**：[填写具体数字]
- **完成指令数**：[填写具体数字]
- **CPI**：[填写具体数字]
- **数据停顿**：0 次（无依赖关系）
- **控制停顿**：0 次（无分支跳转）
- **转发次数**：0 次

**流水线时空图分析：**

```
指令 \ 周期    CC1    CC2    CC3    CC4    CC5    CC6    CC7    CC8
addi r1,...    IF     ID     EX     MEM    WB
addi r2,...           IF     ID     EX     MEM    WB
addi r3,...                  IF     ID     EX     MEM    WB
add r10,...                       IF     ID     EX     MEM    WB
```

每周期推进一段，第 5 周期后流水线填满，之后每周期完成一条指令，CPI 趋近于 1。4 条指令共需 8 周期（首次指令需 5 周期填满流水线 + 3 周期逐条退出），CPI = 8 / 4 = 2.0。但对于长程序，流水线填满后 CPI 趋近于 1.0。

#### 5.1.2 模拟器 B 执行过程

> **[此处粘贴模拟器 B 的截图]**

**执行分析**：

---

### 5.2 场景二：RAW 数据冲突

#### 5.2.1 开启 Forwarding 时的执行过程

> **[此处粘贴模拟器 A 开启 Forwarding 的截图]**
>
> 截图需展示：时空图中 `add r1, r2, r3` 与 `add r4, r1, r5` 之间的转发箭头，
> 以及 `lw r1, 0(r2)` 与 `add r3, r1, r4` 之间的 1 周期停顿。

**流水线时空图分析（开启 Forwarding）：**

```
指令 \ 周期    CC1    CC2    CC3    CC4    CC5    CC6    CC7    CC8    CC9
addi r2,...    IF     ID     EX     MEM    WB
addi r3,...           IF     ID     EX     MEM    WB
add r1,r2,r3                 IF     ID     EX     MEM    WB
add r4,r1,r5                       IF     ID     EX     MEM    WB
                                                          ↑
                                                    Forwarding: r1 从 EX/MEM 转发
lw r1,0(r2)                           IF     ID     EX     MEM    WB
add r3,r1,r4                                 IF     ID    STALL  EX     MEM    WB
                                                             ↑
                                                  Load-Use 停顿 1 周期
```

**转发路径的代码实现分析：**

`add r1, r2, r3` 在 EX 段计算出 `r1 = r2 + r3` 时，结果存入 `ex_mem.alu_result`。下一条 `add r4, r1, r5` 在 ID 段时，EX 段检测到 `rs(r1) == ex_mem.rd(r1)`，触发转发（优先级 1，EX/MEM → EX）：

```python
if (self.ex_mem.op and self.ex_mem.reg_write and self.ex_mem.rd is not None
        and self.ex_mem.rd == rs and rs != 0):
    return self.ex_mem.alu_result, True, self.ex_mem.instr_addr, "EX"
```

`lw r1, 0(r2)` 在 MEM 段才能获得内存数据，因此当 `add r3, r1, r4` 进入 ID 段时，检测到 `rs(r1) == ex_mem.rd(r1)` **且** `ex_mem.mem_read == True`（即 EX/MEM 中的指令是 `lw`），触发 Load-Use 停顿：

```python
if self.ex_mem.mem_read:
    if (op in ("add", ...) and rs == ex_dst) or ...:
        stall_needed = True
```

**为什么 `lw → add` 即使转发也无法完全消除停顿？**

这是由硬件时序决定的：

```
周期边界       EX 段开始               EX 段结束               MEM 段结束
                │                       │                       │
lw 指令         │   ALU 计算地址         │   MEM: 读内存          │   WB: 写回
                │                       │   ↑ 数据此时才拿到     │
                │                       │   转发到 ALU         ←─如果转发到 ALU
                │                       │   必须等这个周期结束  →  晚了一个周期
                │                       │                       │
add 依赖指令     │   ALU 需要 r1 的值    │                       │
                │   但还没算出来         │                       │
                ↓                       ↓                       ↓
```

关键在于：`lw` 的 ALU 阶段只计算**内存地址**，真正从内存读数据发生在 **MEM 段**。而 `add r3, r1, r4` 的 ALU 需要 r1 的值作为**运算源操作数**，这个值在 `lw` 的 MEM 段结束前都不存在。所以无论转发路径多快，在 `lw` 的 MEM 段完成前，`add` 都无法开始执行——必须插入**至少 1 个周期的停顿**。

**转发路径的完整调用链路（以 `add r4, r1, r5` 为例）：**

```
周期 4（add r4, r1, r5 进入 ID 段时）:
  _step_id() → 冒险检测发现 r1 == ex_mem.rd（来自 add r1,r2,r3）
             → forwarding_on == True 且 ex_mem.mem_read == False
             → 无需停顿，正常推进

周期 5（add r4, r1, r5 进入 EX 段时）:
  _step_ex() → _forward_alu_a(rs=1)
             → ex_mem.rd == 1？是的！→ 返回 ex_mem.alu_result（即 r1 的值 10）
             → reg_a_val 被覆盖为转发值
             → ALU.add(10, r5) → 计算结果
             → forwarding_saved += 1
             → 记录事件: "Forward: r1 从 EX/MEM 转发到 EX"
```

**Load-Use 停顿的完整调用链路（以 `add r3, r1, r4` 依赖 `lw r1, 0(r2)` 为例）：**

```
周期 6（add r3, r1, r4 进入 ID 段时）:
  _step_id() → 冒险检测发现 r1 == ex_mem.rd（来自 lw r1,0(r2)）
             → ex_mem.mem_read == True（是 lw 指令！）
             → stall_needed = True（Load-Use 停固定停 1 周期）
             → id_ex.op = None（气泡），_stall_pc = True（PC 停止）
             → load_use_stalls += 1

周期 7（add r3, r1, r4 仍停留在 ID 段，重复译码）:
  lw 已经进入 MEM 段，ex_mem.mem_read 失效
  不再匹配 Load-Use，正常推进

周期 8（add r3, r1, r4 进入 EX 段）:
  _step_ex() → _forward_alu_a(rs=1)
             → 现在 lw 在 MEM/WB 段，mem_to_reg=True
             → 转发 mem_data（即 lw 从内存读出的值）
             → ALU 计算
```

**事件日志（参考格式）：**
```
[C5] Forward: r1 从 EX/MEM 转发到 EX    ← add→add 转发
[C8] Load-Use stall: add ... 等待 r1    ← lw→add 停顿
```

#### 5.2.2 关闭 Forwarding 时的执行过程

> **[此处粘贴模拟器 A 关闭 Forwarding（FWD: OFF）的截图]**

**流水线时空图分析（关闭 Forwarding）：**

```
指令 \ 周期    CC1    CC2    CC3    CC4    CC5    CC6    CC7    CC8    CC9    CC10
addi r2,...    IF     ID     EX     MEM    WB
addi r3,...           IF     ID     EX     MEM    WB
add r1,r2,r3                 IF     ID     EX     MEM    WB
add r4,r1,r5                       IF     ID    STALL  STALL  EX     MEM    WB
                                                      ↑
                                                 无转发：r1 需等 WB 段写回
```

**停顿原因：** 关闭 Forwarding 后，`add r4, r1, r5` 在 ID 段检测到依赖 EX/MEM 段的 r1（第 417-423 行），由于没有转发通路，触发 RAW 停顿：

```python
elif not self.forwarding_on:
    if (op in ("add", "addi", "lw", "sw", "beqz") and rs == ex_dst) or \
       (op in ("add", "sw", "beqz") and rt == ex_dst):
        stall_needed = True
        self.events.append(f"RAW stall: {instr['text']} 等待 r{ex_dst} (无转发)")
        self.stats.data_stalls += 1
```

注意这里检测的是 **EX/MEM 段**（正在 MEM 段的指令也有 raw 依赖）。无转发时，`add r1, r2, r3` 在 EX 段计算出结果后，还要经过 MEM 和 WB 两个段才能写回寄存器。`add r4, r1, r5` 必须等待 r1 写回后，从寄存器堆读：

```
        CC3         CC4         CC5         CC6
       ┌──────┐    ┌──────┐    ┌──────┐    ┌──────┐
add r1:│  EX  │ →  │ MEM  │ →  │ WB───┼───→│regs[1]│  ← 值写回寄存器
       └──────┘    └──────┘    └──────┘    └──────┘
                                        ↑
add r4:                         ID     [STALL] [STALL]  EX
                                ↑ 检测到 r1 是 ex_mem.rd 且无转发 → 停顿2周期
```

- **第 4 周期**：`add r4` 在 ID 段，检测到 `ex_mem.rd(r1) == rs(r1)` 且无转发，停顿。等待 `add r1` 离开 EX/MEM。
- **第 5 周期**：`add r4` 仍然在 ID 段，检测到 `mem_wb.rd(r1) == rs(r1)` 且无转发（第 427-433 行），继续停顿。等待 `add r1` 离开 MEM/WB。
- **第 6 周期**：`add r1` 在 WB 段写回 r1 值（`_step_wb` 第 289 行），同时 `add r4` 终于可以在 ID 段正常译码从寄存器读出 r1。
- **第 7 周期**：`add r4` 进入 EX 段执行，共浪费 2 周期。

**2 周期停顿的通用规律**：无转发时，EX 段的后一条指令需要等到前一条的 ALU 结果经历 MEM 段 → WB 写回后才能读到，即 `add: EX → MEM → WB → regs[rs]` 这 3 步中，EX 段结果在周期末产生，需要 2 个完整周期的等待。

**关闭 Forwarding 对两个 RAW 子场景的影响汇总：**

| 子场景 | 停顿周期数 | 原因 |
|-------|:---------:|------|
| `add → add`（2a） | 2 周期 | 等 EX → MEM → WB → 写回寄存器 |
| `lw → add`（2b） | 3 周期 | lw 结果在 MEM 段未才可用，再加 MEM → WB 写回等待 |

#### 5.2.3 模拟器 B 执行过程

> **[此处粘贴模拟器 B 对应场景的截图]**

**对比分析**：

---

### 5.3 场景三：分支跳转（控制冲突）

#### 5.3.1 分支成立（跳转）

> **[此处粘贴模拟器 A 的截图，展示分支跳转后的时空图]**
>
> 重点展示：beqz 指令、被冲刷的指令（划线标记）、跳转目标指令

**流水线时空图分析（跳转）：**

```
指令 \ 周期    CC1    CC2    CC3    CC4    CC5    CC6    CC7
addi r1,...    IF     ID     EX     MEM    WB
beqz r1,8             IF     ID     EX     MEM    WB
add r2,r3,r4                 IF     ID    [冲刷]          ← 被冲刷
add r5,r6,r7                       IF    [冲刷]          ← 被冲刷
add r8,r9,r10                            IF     ID     EX     MEM    WB
                                                    ↑ 跳转目标
```

**跳转逻辑的代码实现（第 360-370 行）：**

```python
elif op == "beqz":
    alu_result = reg_a_val
    if reg_a_val == 0:                    # 分支条件成立
        target = self.id_ex.instr_addr + 4 + self.id_ex.imm  # 计算目标地址
        self.pc.set(target)               # PC 立即跳转
        self._flush_id = True              # 设置冲刷标志
        self.if_id.instruction = None      # 清空 IF/ID（IF 段断流）
        self.events.append(f"Branch taken: beqz 跳转到 0x{target:04X}，冲刷 IF/ID")
        self.stats.control_stalls += 2     # 浪费 2 周期
```

`beqz` 在 EX 段判断条件（`reg_a_val == 0`）为真时：
1. 计算跳转目标地址 `target = instr_addr + 4 + imm`
2. 将 PC 直接设置为该目标地址（不走 `PC.next()`）
3. 设置 `_flush_id = True`，下一周期 ID 段将清空 ID/EX 寄存器
4. 清空 `if_id.instruction`，使 IF 段在该周期取指时取目标地址的指令

此时 IF 和 ID 段中分别错误地取入了 `add r2, r3, r4` 和 `add r5, r6, r7`，这两条指令将被冲刷——它们虽然在物理上被取入了段间寄存器，但不会进入 EX 段执行。

**ID 段的冲刷处理（第 385-389 行）：**

```python
if self._flush_id:
    self.id_ex.op = None           # ID/EX 清空 = 插入 2 个气泡
    self._flush_id = False
    self._id_instruction = None
    return
```

`_flush_id` 标志使 ID 段跳过正常译码，直接将 ID/EX 寄存器置空（第 386 行），模拟硬件中段间寄存器的清零信号。

#### 5.3.2 分支不成立（不跳转）

> **[此处粘贴模拟器 A 的截图，展示分支不跳转的时空图]**
>
> （可将 `addi r1, r0, 0` 改为 `addi r1, r0, 1` 使 beqz 不跳转）

**分析**：条件不成立时，`reg_a_val != 0`，跳过第 363-368 行的跳转逻辑，流水线正常推进。`add r2, r3, r4` 和 `add r5, r6, r7` 正常执行，**无停顿开销**。

#### 5.3.3 模拟器 B 执行过程

> **[此处粘贴模拟器 B 对应场景的截图]**

**对比分析**：

---

## 6. 性能统计对比

### 6.1 模拟器 A 性能数据

| 场景 | 总周期 | 指令数 | CPI | 数据停顿 | Load-Use 停顿 | 控制停顿 | 转发避免 |
|------|--------|--------|-----|----------|---------------|----------|----------|
| 无冲突 | | | | 0 | 0 | 0 | 0 |
| RAW（开FWD） | | | | | | 0 | |
| RAW（关FWD） | | | | | | 0 | 0 |
| 分支跳转 | | | | 0 | 0 | | 0 |

> 请在运行模拟器后填写实际数据。

### 6.2 模拟器 B 性能数据

| 场景 | 总周期 | CPI | 数据停顿 | 控制停顿 |
|------|--------|-----|----------|----------|
| 无冲突 | | | | |
| RAW 冲突 | | | | |
| 分支跳转 | | | | |

> 请在模拟器 B 上运行相同测试代码后填写。

### 6.3 对比分析

> 对比两个模拟器在相同场景下的性能差异，分析可能的原因。

---

## 7. 实验感悟

> 以下为参考提纲，请结合自己的实际体验撰写（不少于 200 字）：

1. **对流水线冲突的理解**：通过实际运行模拟器，观察流水线在不同冲突场景下的行为（停顿、转发、冲刷），对课本中的理论概念有了哪些更深入的认识？

2. **Forwarding 技术的效果**：对比开启和关闭 Forwarding 时的性能差异，Forwarding 对哪些冲突有效？对哪些冲突无效（如 Load-Use）？为什么？

3. **分支预测的意义**：分支跳转带来的控制冲突浪费了多少周期？在现代处理器中，更高级的分支预测（如动态预测）能带来什么收益？

4. **模拟器实现的收获**：在自研模拟器的过程中，对流水线段间寄存器、控制信号生成、冒险检测逻辑有了哪些理解上的提升？结合 `pipeline.py` 中的具体代码（如 `_gen_controls()` 的控制信号组合、`_forward_alu_a()` 的三级转发优先级、`_step_ex()` 中 beqz 的冲刷逻辑等），说明你对硬件设计在不同抽象层次上的理解。

5. **两个模拟器的对比**：自研模拟器与开源模拟器在功能、易用性、可视化等方面的差异和各自的优缺点。

---

## 附录

### A. 模拟器 A 运行说明

```bash
cd five_stage_pipeline/
python3 app.py
# 浏览器打开 http://localhost:8080
```

### B. 模拟器 B 运行说明

> 此处填写模拟器 B 的下载/安装方式、启动命令、加载程序步骤。

### C. 主要参考资料

1. 计算机组成与设计（ Patterson & Hennessy ）— 流水线章节
2. MIPS32 指令集架构参考
3. 上机实验 2 实验指导书
