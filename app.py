"""Flask API：将流水线模拟器封装为 Web 服务"""

import os
from flask import Flask, jsonify, request, send_from_directory
from pipeline import PipelineSimulator
from assembler import parse_program, parse_line

app = Flask(__name__)
sim = PipelineSimulator()


# ─── 页面路由 ──────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')


# ─── API 路由 ──────────────────────────────────

@app.route('/api/state', methods=['GET'])
def api_state():
    return jsonify(sim.get_snapshot())


@app.route('/api/step', methods=['POST'])
def api_step():
    sim.step()
    return jsonify(sim.get_snapshot())


@app.route('/api/run', methods=['POST'])
def api_run():
    sim.running = True
    sim.paused_by = None
    # 执行一个周期后返回，前端用轮询方式继续
    if not sim._all_done():
        sim.step()
    if sim._all_done():
        sim.running = False
        sim.paused_by = "complete"
    return jsonify(sim.get_snapshot())


@app.route('/api/pause', methods=['POST'])
def api_pause():
    sim.running = False
    sim.paused_by = "user"
    return jsonify(sim.get_snapshot())


@app.route('/api/reset', methods=['POST'])
def api_reset():
    instructions = sim.instructions.copy() if sim.instructions else []
    sim.reset()
    if instructions:
        sim.load_program(instructions)
    return jsonify(sim.get_snapshot())


@app.route('/api/load', methods=['POST'])
def api_load():
    data = request.get_json()
    if not data:
        return jsonify({"error": "请求体为空"}), 400

    code = data.get('code', '')
    filename = data.get('filename', '')

    # 如果指定了文件名，从 test_programs 目录加载
    if filename and not code:
        filepath = os.path.join('test_programs', filename)
        if not os.path.exists(filepath):
            return jsonify({"error": f"文件不存在: {filename}"}), 404
        with open(filepath, 'r') as f:
            code = f.read()

    if not code.strip():
        return jsonify({"error": "程序为空"}), 400

    try:
        instructions = parse_program(code)
        sim.load_program(instructions)
        return jsonify(sim.get_snapshot())
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route('/api/forwarding', methods=['POST'])
def api_forwarding():
    data = request.get_json()
    if data and 'enabled' in data:
        sim.forwarding_on = data['enabled']
    else:
        sim.toggle_forwarding()
    return jsonify(sim.get_snapshot())


@app.route('/api/breakpoint/set', methods=['POST'])
def api_breakpoint_set():
    data = request.get_json()
    if not data:
        return jsonify({"error": "请求体为空"}), 400

    bp_type = data.get('type', 'pc')
    if bp_type == 'pc':
        addr = data.get('address')
        if addr is not None:
            sim.set_pc_breakpoint(int(addr))
    elif bp_type == 'stage':
        stage = data.get('stage')
        if stage:
            sim.set_stage_breakpoint(stage)
    return jsonify(sim.get_snapshot())


@app.route('/api/breakpoint/del', methods=['POST'])
def api_breakpoint_del():
    data = request.get_json()
    if not data:
        return jsonify({"error": "请求体为空"}), 400

    bp_type = data.get('type', 'pc')
    if bp_type == 'pc':
        addr = data.get('address')
        if addr is not None:
            sim.del_pc_breakpoint(int(addr))
    elif bp_type == 'stage':
        stage = data.get('stage')
        if stage:
            sim.del_stage_breakpoint(stage)
    return jsonify(sim.get_snapshot())


@app.route('/api/files', methods=['GET'])
def api_files():
    """返回 test_programs 目录下的预设文件列表"""
    test_dir = 'test_programs'
    if not os.path.exists(test_dir):
        return jsonify([])
    files = [f for f in os.listdir(test_dir) if f.endswith('.txt')]
    return jsonify(sorted(files))


@app.route('/api/stats', methods=['GET'])
def api_stats():
    snap = sim.get_snapshot()
    return jsonify(snap['stats'])


# ─── 启动 ──────────────────────────────────────

if __name__ == '__main__':
    print("=" * 55)
    print("  MIPS 5-Stage Pipeline Simulator")
    print("  浏览器打开: http://localhost:8080")
    print("=" * 55)
    app.run(host='0.0.0.0', port=8080, debug=True)
