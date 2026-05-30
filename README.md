# 模拟器A — MIPS 五段流水线模拟器 工作方案

## 技术选型

| 项目 | 选择 | 理由 |
|------|------|------|
| 后端 | Python 3 + Flask | 轻量 Web 框架，适合单文件 API 服务 |
| 前端 | 单个 HTML 文件（原生 HTML/CSS/JS） | 无框架依赖，表格+按钮+CSS div 即可实现全部交互 |
| 运行方式 | `python app.py` 本地启动 | 轻量，无需容器化 |
| 体系结构 | MIPS32（32位） | 32个32位通用寄存器，32位地址空间，定长32位指令 |

## 项目文件结构

```
five_stage_pipeline/
├── requirements.txt        # Python 依赖：flask
├── app.py                  # Flask 入口：API 路由 + 启动服务器
├── pipeline.py             # 流水线核心：5段逻辑 + 段间寄存器 + 冲突处理
├── datapath.py             # 数据通路：寄存器堆、内存、ALU、PC
├── assembler.py            # 汇编器：MIPS 指令文本 → 内部表示
├── templates/
│   └── index.html          # 前端页面：4面板仪表盘 + 交互控制
└── test_programs/
    ├── no_hazard.txt       # 场景1：无冲突
    ├── raw_hazard.txt      # 场景2：RAW冲突（含 add→add 和 lw→add）
    └── branch.txt          # 场景3：分支跳转
```

---

## 架构概览

```
浏览器                          Flask 服务（本地）
┌─────────────────┐    HTTP     ┌──────────────────────┐
│  index.html     │ ←──────────→│  Flask (app.py)      │
│  HTML/CSS/JS    │   JSON API  │      ↓               │
│                 │             │  pipeline.py         │
│  4面板仪表盘      |             │      ↓               │
│  鼠标点击操控     │             │  datapath.py         │
│                 │             │  assembler.py        │
└─────────────────┘             └──────────────────────┘
```

- 后端完全不关心前端怎么渲染，只管计算流水线状态并返回 JSON
- 前端完全不关心流水线怎么实现，只管请求 JSON 然后画到屏幕上
- 两者通过 REST API 通信，数据格式为 `SimulationSnapshot` JSON

---

## Step 1：数据通路基础（datapath.py）

**目标**：搭建 MIPS 核心硬件组件

### 实现内容
- **寄存器堆**（32个32位寄存器，`$0` 恒为0）
- **指令内存**（数组模拟，按地址索引）
- **数据内存**（数组模拟，支持 `lw`/`sw`）
- **PC**（程序计数器）
- **ALU**（支持 `add`、`sub` 运算）

### 验证标准
- 能读写寄存器、内存
- ALU 能正确计算 `add`/`sub`
- 单元测试通过

---

## Step 2：指令集支持（assembler.py + pipeline.py 骨架）

**目标**：支持4条指令的解析与执行

### 实现内容
- **指令格式**：`add $rd, $rs, $rt` / `lw $rt, offset($rs)` / `sw $rt, offset($rs)` / `beqz $rs, offset`
- **beqz 跳转目标**：使用**数值偏移**（字节偏移量），跳转地址 = `PC + 4 + offset`
  - 例如 `beqz $1, 8` 表示 `$1==0` 时跳转到 `PC+4+8`
  - 避免引入标签/符号表解析，降低复杂度
- 指令解析 → 内部表示（opcode + 寄存器编号 + 立即数）

### 验证标准
- 4条指令解析正确
- 单条指令在无流水线模式下能正确执行（寄存器/内存结果正确）

---

## Step 3：五段流水线骨架（pipeline.py）

**目标**：搭建 IF/ID/EX/MEM/WB 五段流水线框架

### 实现内容
- **段间寄存器**：IF/ID、ID/EX、EX/MEM、MEM/WB
- **每段功能**：
  - IF：取指，PC+4
  - ID：译码，读寄存器
  - EX：ALU 运算，计算分支目标地址
  - MEM：数据内存读写
  - WB：写回寄存器
- **流水线推进**：每个时钟周期，段间寄存器向后传递
- 初始状态全部为空泡（NOP/bubble）

### 验证标准
- 指令能逐段推进
- 段间寄存器正确传递数据
- 多周期后指令从 WB 段退出

---

## Step 4：冲突检测与处理（pipeline.py 扩展）

**目标**：检测并处理 RAW 数据冲突和控制冲突

### 数据冲突（RAW）

- **检测时机**：ID 段检查源寄存器是否与 EX/MEM 或 MEM/WB 段的目标寄存器匹配
- **定向（Forwarding）**：
  - 可配置开关（网页按钮切换）
  - 开启时：ALU 输入可来自 EX/MEM 或 MEM/WB 的转发路径
  - `add → add`：前向通路可完全消除停顿
- **Load-Use 冲突**：
  - `lw` 的结果在 MEM 段才可用，即使开启 forwarding，后续依赖指令仍需停顿 1 周期
  - 这是演示 RAW 冲突的**典型场景**
- **停顿实现**：插入气泡（将 ID/EX 寄存器清零），PC 不更新（IF 段重复取同一条指令）

### 控制冲突（beqz）

- **策略**：假设分支不跳转（Predict Not Taken）
  - 分支指令进入 ID 段时，继续取 `PC+4`
  - 分支指令在 EX 段计算出结果后：
    - 不跳转：流水线正常继续
    - 跳转：冲刷 IF/ID 段（插入2个气泡），PC 更新为跳转目标地址
- **性能统计**：记录因分支跳转浪费的周期数

### 验证标准
- `add → add` RAW 冲突：关闭 forwarding 时有停顿，开启后无停顿
- `lw → add` Load-Use：无论 forwarding 开关，均有 1 周期停顿
- `beqz` 跳转时正确冲刷+跳转，不跳转时无开销

---

## Step 5：Flask API 层（app.py）

**目标**：将流水线引擎封装为 REST API，供 Web 前端调用

### API 路由

| 方法 | 路径 | 功能 | 请求体 |
|------|------|------|--------|
| `GET` | `/api/state` | 获取当前完整状态 | — |
| `POST` | `/api/step` | 单步执行一个周期 | — |
| `POST` | `/api/run` | 连续执行到结束/断点 | — |
| `POST` | `/api/pause` | 暂停连续执行 | — |
| `POST` | `/api/reset` | 重置模拟器 | — |
| `POST` | `/api/load` | 载入程序 | `{ "code": "..." }` 或 `{ "filename": "xxx.txt" }` |
| `POST` | `/api/forwarding` | 切换 forwarding | `{ "enabled": true/false }` |
| `POST` | `/api/breakpoint/set` | 设置PC地址断点 | `{ "type": "pc", "address": 8 }` |
| `POST` | `/api/breakpoint/set` | 设置流水段断点 | `{ "type": "stage", "stage": "EX" }` |
| `POST` | `/api/breakpoint/del` | 删除断点 | `{ "type": "pc", "address": 8 }` 或 `{ "type": "stage", "stage": "EX" }` |
| `GET` | `/` | 返回 index.html 页面 | — |

### 返回数据格式

```json
{
  "cycle": 12,
  "pc": 32,
  "forwarding_on": true,
  "running": false,
  "paused_by": null,
  "breakpoints": {
    "pc": [8, 16],
    "stages": ["EX"]
  },
  "stages": {
    "IF":  { "instr": "lw $5,4($0)", "pc": 36, "bubble": false },
    "ID":  { "instr": "add $2,$1,$3", "pc": 32, "bubble": false },
    "EX":  { "instr": "beqz $1,8", "pc": 28, "bubble": false },
    "MEM": { "instr": "sw $5,0($2)", "pc": 24, "bubble": false },
    "WB":  { "instr": null, "pc": null, "bubble": true }
  },
  "pipeline_regs": {
    "IF_ID": {
      "pc_plus_4": 40,
      "instruction": "lw $5,4($0)"
    },
    "ID_EX": {
      "pc_plus_4": 36,
      "reg_a": 5,
      "reg_b": 0,
      "imm": 4,
      "rd": 5,
      "rs": 0,
      "rt": 5,
      "controls": { "reg_write": true, "mem_read": true, "mem_write": false, "alu_src": true, "reg_dst": false, "mem_to_reg": true }
    },
    "EX_MEM": {
      "pc_plus_4": 32,
      "alu_result": 8,
      "reg_b": 0,
      "rd": 5,
      "controls": { "reg_write": true, "mem_read": false, "mem_write": true, "mem_to_reg": false }
    },
    "MEM_WB": {
      "pc_plus_4": 28,
      "mem_data": 10,
      "alu_result": 4,
      "rd": 2,
      "controls": { "reg_write": true, "mem_to_reg": true }
    }
  },
  "registers": {"0": 0, "1": 5, "2": 3, "3": 0, "5": 0},
  "instructions": [
    {"addr": 0,  "text": "lw $1, 0($2)",   "stage": "WB", "done": true},
    {"addr": 4,  "text": "add $3, $1, $4", "stage": "MEM", "done": false},
    {"addr": 8,  "text": "beqz $1, 8",     "stage": "EX", "done": false},
    {"addr": 12, "text": "sw $5, 0($2)",   "stage": "ID", "done": false},
    {"addr": 16, "text": "add $6, $7, $8", "stage": "IF", "done": false}
  ],
  "data_memory": {"0": 10, "4": 0, "8": 5},
  "events": ["RAW stall: ID stage blocked", "Forward: $1 from EX/MEM → ID"],
  "stats": {
    "total_cycles": 12,
    "completed_instructions": 6,
    "cpi": 2.0,
    "data_stalls": 2,
    "control_stalls": 1,
    "forwarding_saved": 1
  }
}
```

### 断点机制

支持两种断点类型，可同时生效：

**PC 地址断点**
- 每个时钟周期取指前，比较 `PC` 是否等于任一 PC 断点地址
- stall 导致的重复取指不算命中
- 前端指令列表对应行高亮标记

**流水段断点（段级断点）**
- 用户可选择任意流水段（IF / ID / EX / MEM / WB）设断
- 每个时钟周期结束时检查：该段当前是否包含有效指令（非 bubble）
- 命中条件：设了断点的段 → 该段有指令进入 → 触发暂停
- 例如在 EX 段设断：当 `beqz` 指令推进到 EX 段时自动暂停
- 命中后 `paused_by` 字段返回触发断点的段名

**两种断点同时生效**
- 任一类型命中即暂停
- `paused_by` 字段记录触发原因：`"pc:0x08"` 或 `"stage:EX"`
- 前端暂停时在流水线图高亮命中的段，并用 toast/提示标注触发原因

### 程序载入

支持两种载入方式：

**方式一：文件导入**
- 前端提供文件选择器 `<input type="file">`
- 用户选择 .txt 文件后，前端读取内容发到 `POST /api/load { "code": "..." }`
- 同时 `test_programs/` 目录下的预设文件可通过下拉菜单快速加载

**方式二：直接输入**
- 前端提供 `<textarea>`，用户直接输入/粘贴 MIPS 指令
- 每行一条指令，空行忽略，`#` 开头的行为注释
- 输入完成后点击 [载入] 按钮，内容发到后端解析
- 解析成功 → 更新所有面板；解析失败 → 前端显示错误行号和原因

**错误处理**
- 后端汇编器解析失败时返回 `{ "error": "第3行：无法识别的指令 'sub'", "line": 3 }`
- 前端在指令输入区下方红色显示错误信息，标出问题行

### 验证标准
- `GET /api/state` 返回正确 JSON
- `POST /api/step` 后 cycle+1，流水线推进
- `POST /api/load` 支持文件内容载入，非法指令返回错误
- PC 断点命中后 `run` 自动停止，`paused_by` = `"pc:0x08"`
- 段断点命中后自动停止，`paused_by` = `"stage:EX"`
- 程序执行完毕（所有指令 WB 退出）后 `running` 自动变为 `false`

---

## Step 6：Web 前端仪表盘（templates/index.html）

**目标**：单个 HTML 文件实现四面板仪表盘，鼠标点击操控，实时彩色刷新

---

### 6.1 页面整体布局（CSS Grid）

```
┌──────────────────────────────────────────────────────────────────┐
│  MIPS 五段流水线模拟器              周期:12   FWD: 开启          │
├─────────────────────────────┬────────────────────────────────────┤
│                             │                                    │
│   流水线运行示意图           │   寄存器堆                         │
│   ╔══════╗   ╔══════╗     │   ┌────┬───────┬────┬───────┐     │
│   ║  IF  ║──→║  ID  ║─→   │   │ $0 │ 0x0000│ $1 │ 0x0005│     │
│   ║ lw   ║   ║ add  ║     │   │ $2 │ 0x0003│ $3 │ 0x0000│     │
│   ║0x0010║   ║0x000C║     │   │ $4 │ 0x000A│ $5 │ 0x0000│     │
│   ╚══════╝   ╚══════╝     │   │ ...                          │
│       │  ┌──────┘ │        │                                    │
│       ↓  ↓ FWD   ↓        │                                    │
│   ╔══════╗   ╔══════╗     │                                    │
│   ║  EX  ║──→║ MEM  ║─→   │                                    │
│   ║ beqz ║   ║  sw  ║     │                                    │
│   ║0x0008║   ║0x0004║     │                                    │
│   ╚══════╝   ╚══════╝     │                                    │
│       │          │         │                                    │
│       ↓          ↓         │                                    │
│   ╔══════╗                 │                                    │
│   ║  WB  ║   BUBBLE        │                                    │
│   ║ (空) ║                 │                                    │
│   ╚══════╝                 │                                    │
│ ── 段间寄存器 ──────────────────────────────────────────────    │
│  IF/ID: [PC+4:0x14] [IR:lw $5,4($0)]                           │
│  ID/EX: [PC+4:0x10] [RegA=5] [RegB=0] [Imm=4]                 │
│         [ctrl: RegW✓ MemR✓ MemW✗ ALUSrc✓]                      │
│  EX/MEM:[ALUout=8] [RegB=0] [dst=$5]                           │
│         [ctrl: RegW✓ MemW✓]                                     │
│  MEM/WB:[MemData=10] [ALUout=4] [dst=$2]                       │
│         [ctrl: RegW✓ MemtoReg✓]                                 │
│                             │                                    │
├─────────────────────────────┼────────────────────────────────────┤
│                             │                                    │
│   指令列表                   │   数据内存                         │
│   地址    指令        段    │   地址       值                    │
│   0x00  lw $1,0($2)  [DONE]│   0x00    0x0000000A              │
│   0x04  sw $5,0($2)  [MEM] │   0x04    0x00000000              │
│   0x08  beqz $1,8    [EX]  │   0x08    0x00000005              │
│   0x0C  add $2,$1,$3 [ID]  │   0x0C    0x00000000              │
│ ▶ 0x10  lw $5,4($0)  [IF]  │   0x10    0x00000000              │
│                             │                                    │
├─────────────────────────────┴────────────────────────────────────┤
│ [单步] [▶运行] [⏸暂停] [↺重置] 速度:[====○====]                │
│ Forwarding: [ON ●]                                             │
│ ─────────────────────────────────────────────────────────────── │
│ PC断点: [0x08 ×] [输入地址:____] [添加]                         │
│ 段断点: ☑IF ☑ID ☐EX ☐MEM ☐WB                                  │
│ ─────────────────────────────────────────────────────────────── │
│ 载入程序: [选择文件] [▼预设文件] 或直接输入:                     │
│ ┌─────────────────────────────────────────────────────────┐    │
│ │ add $1,$2,$3                                            │    │
│ │ lw  $4,0($1)                                            │    │
│ └─────────────────────────────────────────────────────────┘    │
│ [载入] [清空]                                                    │
│ ─────────────────────────────────────────────────────────────── │
│ 事件日志:                                                        │
│ [Cycle 5] RAW stall: 指令0x0C在ID段等待$1 (来自lw MEM段)       │
│ [Cycle 6] Forward: $1 从 MEM/WB → ID 段                        │
│ [Cycle 8] 断点命中: Stage=EX, 指令=0x08 beqz $1,8              │
└──────────────────────────────────────────────────────────────────┘
```

---



### 6.1a 段间寄存器详情面板

位于流水线图正下方，水平排列 4 个段间寄存器卡片，展示每个流水线锁存器的完整内部值。

**显示格式（HTML）：**

```html
<div class="pipeline-regs-row">
  <!-- IF/ID -->
  <div class="preg-card preg-ifid">
    <div class="preg-title">IF/ID</div>
    <div class="preg-fields">
      <span>PC+4: 0x0014</span>
      <span>IR: lw $5,4($0)</span>
    </div>
  </div>
  <div class="preg-arrow">→</div>
  <!-- ID/EX -->
  <div class="preg-card preg-idex">
    <div class="preg-title">ID/EX</div>
    <div class="preg-fields">
      <span>PC+4: 0x0010</span>
      <span>RegA: $1 = 5</span>
      <span>RegB: $3 = 0</span>
      <span>Imm: 4</span>
      <span class="preg-ctrl">ctrl: RegW✓ MemR✓ ALUSrc✓</span>
    </div>
  </div>
  <div class="preg-arrow">→</div>
  <!-- EX/MEM -->
  <div class="preg-card preg-exmem">
    <div class="preg-title">EX/MEM</div>
    <div class="preg-fields">
      <span>ALUOut: 8</span>
      <span>RegB: $5 = 0</span>
      <span>dst: $5</span>
      <span class="preg-ctrl">ctrl: RegW✓ MemW✓</span>
    </div>
  </div>
  <div class="preg-arrow">→</div>
  <!-- MEM/WB -->
  <div class="preg-card preg-memwb">
    <div class="preg-title">MEM/WB</div>
    <div class="preg-fields">
      <span>MemData: 10</span>
      <span>ALUOut: 4</span>
      <span>dst: $2</span>
      <span class="preg-ctrl">ctrl: RegW✓ MemtoReg✓</span>
    </div>
  </div>
</div>
```

**4 个段间寄存器各自包含的字段：**

| 寄存器 | 包含字段 | 说明 |
|--------|---------|------|
| **IF/ID** | PC+4, IR（指令文本） | 取指结果传入译码段 |
| **ID/EX** | PC+4, RegA(rs值), RegB(rt值), Imm(立即数), rd/rs/rt 寄存器号, 控制信号(RegWrite/MemRead/MemWrite/ALUSrc/RegDst/MemtoReg) | 译码结果传入执行段 |
| **EX/MEM** | ALUOut(ALU结果), RegB(存储数据), rd(目标寄存器), 控制信号(RegWrite/MemRead/MemWrite/MemtoReg) | 执行结果传入访存段 |
| **MEM/WB** | MemData(内存读出), ALUOut, rd(目标寄存器), 控制信号(RegWrite/MemtoReg) | 访存结果传入写回段 |

**CSS 样式要点：**
- 每个卡片边框颜色对应**数据来源段**的颜色（如 ID/EX 卡片用 ID 的绿色）
- 控制信号字段用 ✓（绿色）和 ✗（红色）标识，一目了然
- 气泡段对应的流水线寄存器卡片灰色淡化（如 ID 段为 bubble 时 IF/ID 寄存器无新数据）
- 转发的值在卡片中用特殊标记（如 `RegA: $1 = 5 ← FWD from EX/MEM`）
- 卡片之间用 `→` 箭头连接

**交互特性：**
- 段间寄存器卡片跟随流水线图每个周期更新
- 转发的数据流用蓝色虚线箭头从源寄存器卡片指向目的寄存器卡片
- 当某段暂停/冲刷时，对应段间寄存器的卡片边框闪烁

---

### 6.2 流水线运行示意图（核心面板）

**五段配色方案：**

| 流水段 | 颜色 | 色值 | CSS class |
|--------|------|------|-----------|
| IF | 蓝色 | `#4A90D9` | `.stage-if` |
| ID | 绿色 | `#5CB85C` | `.stage-id` |
| EX | 橙色 | `#F0AD4E` | `.stage-ex` |
| MEM | 红色 | `#D9534F` | `.stage-mem` |
| WB | 紫色 | `#9B59B6` | `.stage-wb` |
| Bubble/空 | 灰色 | `#CCCCCC` | `.stage-bubble` |

**每段方框结构（HTML）：**
```html
<div class="stage-box stage-if">
  <div class="stage-label">IF</div>
  <div class="stage-instr">lw $5,4($0)</div>
  <div class="stage-pc">0x0010</div>
</div>
```

CSS 样式要点：
- `border: 3px solid` 对应颜色，`border-radius: 8px`
- 背景为颜色 15% 透明度的浅色底
- 段标签（IF/ID/EX/MEM/WB）在方框顶部，粗体白字，彩色背景
- 气泡段：灰色边框+灰色文字，"BUBBLE" 代替指令，背景白色
- 当前暂停命中的段：`box-shadow: 0 0 12px` 发光效果 + `animation: pulse 0.8s` 闪烁

**段间连接箭头（CSS）：**
- 水平连接（IF→ID、ID→EX、EX→MEM、MEM→WB）：`→` 或 CSS `::after` 伪元素画箭头
- Forwarding 旁路路径（开启时显示）：
  - EX/MEM → EX（蓝色虚线箭头，标注 "FWD"）
  - MEM/WB → EX（紫色虚线箭头，标注 "FWD"）
  - 仅当本周期实际发生了转发时才显示，否则隐藏

**冲刷可视化：**
- beqz 跳转发生时，IF 和 ID 段的方框短暂变红 + 抖动动画
- 150ms 后恢复为气泡/下一条指令

**流水线图底层结构：**
```
Flexbox 水平排列： [IF] → [ID] → [EX] → [MEM] → [WB]
                   ↑        ↑       ↑
                  PC+4    译码    ALU/Branch
```
五段始终显示，空的段显示灰色 Bubble 框。

---

### 6.3 寄存器堆面板

**布局：** 8行 × 4列 HTML `<table>`，每格显示 `$N = 0xVVVV`

**交互特性：**
- 当前周期被写入的寄存器：黄色背景闪烁（CSS transition 0.3s），持续一个周期后渐退
- `$0` 始终灰色不可编辑
- 非零寄存器正常黑色；零值寄存器浅灰小字
- 表头行固定（sticky header），表格可滚动

---

### 6.4 指令列表面板

**布局：** HTML `<table>`，列：`地址 | 指令 | 所在段`

**交互特性：**
- 每条指令右侧用对应段的彩色圆角标签标注：[IF] [ID] [EX] [MEM] [WB] [DONE]
- 已完成指令（DONE）整行淡化（opacity: 0.4）
- 当前 PC 指向的指令行前有 `▶` 蓝色箭头标记
- 已被冲刷的指令（因分支跳转未执行）灰色 + 删除线
- 设置了 PC 断点的指令行，地址列显示红色圆点 `●`

---

### 6.5 数据内存面板

**布局：** HTML `<table>`，列：`地址 | 值`

**交互特性：**
- 仅显示被访问过（读或写）的内存地址，未访问的不显示
- 当前周期被写入的地址：绿色背景闪烁
- 当前周期被读取的地址：蓝色背景闪烁

---

### 6.6 控制栏（底部）

#### 运行控制
| 控件 | 功能 | 快捷键 |
|------|------|--------|
| `[单步]` 按钮 | 执行一个周期，更新所有面板 | `Space` |
| `[▶ 运行]` 按钮 | 自动连续推进直到暂停/断点/结束 | `R` |
| `[⏸ 暂停]` 按钮 | 停止连续执行 | `P` |
| `[↺ 重置]` 按钮 | PC=0，清空流水线，cycle=0，保留程序 | — |
| 速度滑块 | 连续运行时周期间隔：100ms(快) ~ 2000ms(慢)，默认 500ms | `+` / `-` |

**运行中状态管理：**
- 点 [运行] 时，前端启动 `setInterval` 循环调 `/api/step`
- 每次 step 返回后检查 `running` 字段：`false` 则自动 clearInterval
- 暂停原因（`paused_by`）在前端以 toast 提示显示：
  - `"stage:EX"` → "断点命中：指令 beqz 进入 EX 段"
  - `"pc:0x08"` → "断点命中：PC = 0x08"
  - `null` + 所有指令 DONE → "程序执行完毕"

#### Forwarding 开关
- Toggle 开关（CSS checkbox hack 或滑动按钮）
- 状态栏实时显示当前状态：`Forwarding: ON ●`（绿色） / `OFF ○`（灰色）

#### 断点设置区
- **PC 断点**：文本输入框（输入十六进制地址如 `0x08`）+ [添加] 按钮
  - 已设断点以 tag 标签显示：`[0x08 ×]` `[0x10 ×]`，点击 × 删除
- **段断点**：5 个 checkbox（☑ IF ☑ ID ☐ EX ☐ MEM ☐ WB）
  - 勾选即生效，取消即删除
  - 例如勾选 EX：当任何有效指令进入 EX 段时自动暂停

#### 程序载入区
- **[选择文件] 按钮**：`<input type="file" accept=".txt">`，选中后自动读取内容到文本框
- **[▼ 预设文件] 下拉菜单**：列出 `test_programs/` 目录下的文件（后端提供 `GET /api/files` 返回文件列表）
  - 选中后自动加载文件内容到文本框
- **文本输入区**：`<textarea>` 6行×60列，等宽字体，直接输入/粘贴 MIPS 指令
- **[载入] 按钮**：将文本框内容发到 `POST /api/load`进行解析和执行
- **[清空] 按钮**：清空文本框
- 加载成功后弹出绿色提示：`✓ 已加载 5 条指令`
- 加载失败弹出红色提示，标出错误行号和原因

#### 事件日志区
- 底部滚动文本区，高度固定约 120px，`overflow-y: auto`
- 每条事件一行，带时间戳（周期号）：
  ```
  [Cycle 5]  RAW stall: 指令 0x0C 在 ID 段等待 $1
  [Cycle 6]  Forward: $1 值 0x0005 从 MEM/WB → ID
  [Cycle 8]  Branch taken: beqz 跳转到 0x14，冲刷 IF/ID
  [Cycle 12] 断点命中: Stage=EX, 指令=beqz $1,8
  [Cycle 15] 程序执行完毕
  ```
- 不同事件类型用不同颜色：
  - Stall → 橙色
  - Forward → 绿色
  - Flush → 红色
  - Breakpoint → 紫色

---

### 6.7 前端 JS 逻辑

```javascript
// 核心数据流
let state = null;                    // 当前 SimulationSnapshot

async function refresh() {           // 获取最新状态
    state = await fetch('/api/state').then(r => r.json());
    renderAll(state);                // 渲染 4 面板 + 事件日志
}

async function step() {              // 单步
    state = await fetch('/api/step', {method:'POST'}).then(r => r.json());
    renderAll(state);
    if (state.paused_by) showPauseReason(state.paused_by);
}

let runTimer = null;
function run() {                     // 连续运行
    runTimer = setInterval(async () => {
        await step();
        if (!state.running) { clearInterval(runTimer); runTimer = null; }
    }, speedMs);
}
function pause() {                   // 暂停
    if (runTimer) { clearInterval(runTimer); runTimer = null; }
}

// 速度控制
let speedMs = 500;
document.getElementById('speed-slider').oninput = e => {
    speedMs = parseInt(e.target.value);
    if (runTimer) { pause(); run(); }  // 运行中则立即生效
};

// 程序载入
async function loadProgram(code) {
    const res = await fetch('/api/load', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({code: code})
    });
    if (!res.ok) {
        const err = await res.json();
        showError(`第${err.line}行: ${err.error}`);
        return;
    }
    await refresh();
    showSuccess(`已加载 ${state.instructions.length} 条指令`);
}

// 段断点
async function toggleStageBreakpoint(stage) {
    const checked = document.getElementById(`bp-stage-${stage}`).checked;
    if (checked) {
        await fetch('/api/breakpoint/set', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({type: 'stage', stage: stage})
        });
    } else {
        await fetch('/api/breakpoint/del', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({type: 'stage', stage: stage})
        });
    }
}
```

### 验证标准
- 四个面板加载后正确显示初始状态
- 点击单步，所有面板同步更新，流水线图指令逐段推进
- 点击运行，流水线图连续动画，点击暂停立即停止
- 段断点勾选 EX 后，指令进入 EX 段时自动暂停 + 高亮
- 载入测试文件后指令列表正确显示
- forwarding 开关切换后流水线停顿行为可见变化
- 非法指令载入时前端正确显示错误信息

---

## Step 7：测试用例 + 性能统计

**目标**：设计3种以上测试场景并实现统计输出

### 测试场景1：无冲突流水线

```asm
add  $1, $2, $3
add  $4, $5, $6
add  $7, $8, $9
add  $10, $11, $12
```
所有指令无依赖关系，流水线满载运行，CPI 接近 1.0。

### 测试场景2：RAW 冲突（含 Load-Use）

**2a. add → add（通过 forwarding 解决）**
```asm
add  $1, $2, $3
add  $4, $1, $5     # 依赖$1，forwarding可消除停顿
```

**2b. lw → add（Load-Use，即使 forwarding 仍需停顿）**
```asm
lw   $1, 0($2)
add  $3, $1, $4     # 依赖$1，即使forwarding也需停顿1周期
```

### 测试场景3：分支跳转

```asm
add  $1, $0, $0     # $1 = 0
beqz $1, 8          # $1==0 成立，跳转到 PC+4+8
add  $2, $3, $4     # （被冲刷）
add  $5, $6, $7     # （被冲刷）
add  $8, $9, $10    # 跳转目标（若偏移=8，即跳过2条指令）
```

### 性能统计输出

页面右下角统计面板（或弹窗）：

```
总执行周期数：         18
完成指令数（WB退出）：   12
CPI（周期/指令）：      1.50
数据冲突停顿周期：       2
  - RAW停顿：           1
  - Load-Use停顿：      1
控制冲突停顿周期：       2
  - 分支跳转冲刷：       2
定向避免的停顿数：       1
```

### 验证标准
- 三种场景均可正常演示
- 性能统计与实际执行一致
- 报告中以网页截图展示执行过程

---

---

## 开发顺序

```
Step 1 (数据通路)
   ↓
Step 2 (指令集)
   ↓
Step 3 (流水线骨架) ←── 至此可以纯 Python 测试流水线
   ↓
Step 4 (冲突处理)   ←── 核心逻辑完成
   ↓
Step 5 (Flask API)  ←── 包裹为 Web 服务
   ↓
Step 6 (HTML 前端)  ←── 可视化仪表盘（可边写边在浏览器调试）
   ↓
Step 7 (测试+统计)
```

- Step 1-4 是纯 Python 逻辑，可以写单元测试验证
- Step 5-6 是 Web 层，浏览器中实时调试
- 直接 `python app.py` 运行即可

---

## 时间估算

| 步骤 | 预估工时 | 难度 | 备注 |
|------|---------|------|------|
| Step 1 数据通路 | 2-3h | ★★ | |
| Step 2 指令集 | 1-2h | ★★ | |
| Step 3 流水线骨架 | 3-4h | ★★★ | |
| Step 4 冲突处理 | 4-5h | ★★★★ | 最复杂的逻辑层 |
| Step 5 Flask API | 2-3h | ★★ | 简单路由，JSON 序列化 |
| Step 6 HTML 前端 | 4-6h | ★★★ | CSS 布局 + 流水线图 + JS 交互 |
| Step 7 测试+统计 | 2-3h | ★★ | |
| 报告撰写 | 4-5h | ★★ | 含网页截图 + 实验分析 |
| **合计** | **22-30h** | | Django/React 方案至少要翻倍 |

---

## 关键设计决策

| 决策 | 选择 | 依据 |
|------|------|------|
| beqz 跳转方式 | 数值偏移 `beqz $rs, offset` | 避免符号表解析 |
| 分支冲突策略 | Predict Not Taken + 跳转时冲刷 | 经典实现，与 forwarding 正交 |
| RAW 测试用例 | 同时含 add→add 和 lw→add | 前者展示 forwarding 消除停顿，后者展示不可避免停顿 |
| 断点判断时机 | 每周期开始，取指前比较 PC | 实现简单，语义清晰 |
| 性能指标 | CPI + 各类停顿周期数 + 定向避免数 | 覆盖 DeepSeek 建议的最小指标集 |
| 前端框架 | 不用，纯原生 HTML/CSS/JS | 对一个小型仪表盘来说框架是过度设计 |
| 数据协议 | JSON REST API | 前后端完全解耦，可独立开发调试 |
| 段间寄存器 | 4组完整展示（IF/ID, ID/EX, EX/MEM, MEM/WB） | 每个周期可见所有锁存器内部值，含控制信号 |
