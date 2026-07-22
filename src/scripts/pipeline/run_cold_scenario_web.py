#!/usr/bin/env python3
"""Local Flask UI for the educational common-cold robot scenario."""

import argparse
import os
import signal
import subprocess
import threading
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request, send_file


PROJECT_ROOT = Path(__file__).resolve().parents[3]
RUNNER = PROJECT_ROOT / "src" / "scripts" / "pipeline" / "run_cold_scenario.sh"
OBJECT_PREVIEW = PROJECT_ROOT / "outputs" / "runtime" / "object_yolo_latest.jpg"
CAMERA_PREVIEW = PROJECT_ROOT / "outputs" / "runtime" / "front_camera_latest.jpg"

app = Flask(__name__)
lock = threading.Lock()
state: dict[str, object] = {
    "process": None,
    "running": False,
    "exit_code": None,
    "logs": ["로컬 교육용 UI가 준비되었습니다. 실제 개인정보는 입력하지 마세요.\n"],
}

PAGE = r"""
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Expert Surgical Mentor</title>
  <style>
    :root { color-scheme: dark; font-family: system-ui, sans-serif; }
    body { margin: 0; background: #10151c; color: #e8edf2; }
    main { max-width: 920px; margin: 32px auto; padding: 0 20px; }
    .card { background: #18212b; border: 1px solid #2c3c4c; border-radius: 14px; padding: 22px; margin-bottom: 18px; }
    h1 { margin-top: 0; font-size: 25px; }
    .grid { display: grid; grid-template-columns: 180px 1fr; gap: 14px; align-items: center; }
    input, select, button { font: inherit; border-radius: 8px; padding: 10px 12px; }
    input, select { border: 1px solid #46596d; background: #0f1720; color: #fff; }
    button { border: 0; cursor: pointer; font-weight: 700; margin-right: 8px; }
    button:disabled { opacity: .5; cursor: default; }
    .dry { background: #8ba4bd; color: #10151c; }
    .run { background: #48c78e; color: #07150f; }
    .stop { background: #ff3b3b; color: #fff; border: 2px solid #ff9a9a; }
    .warning { color: #ffc76b; }
    #status { font-weight: 700; }
    pre { min-height: 260px; max-height: 430px; overflow: auto; background: #080d12; padding: 14px; border-radius: 10px; white-space: pre-wrap; }
    .preview { display: none; width: 100%; max-width: 640px; min-height: 240px; object-fit: contain; background: #080d12; border-radius: 10px; }
    .placeholder { display: grid; place-items: center; width: 100%; max-width: 640px; min-height: 240px; background: #080d12; color: #91a0af; border-radius: 10px; }
    #monitor-step { display: none; }
    .monitor-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; align-items: start; }
    .monitor-grid .card { min-width: 0; }
    .confirm { display: flex; gap: 9px; margin: 18px 0; align-items: flex-start; }
    @media (max-width: 760px) {
      .grid, .monitor-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body><main>
  <section class="card" id="input-step">
    <h1>Expert Surgical Mentor · 감기 시나리오</h1>
    <p class="warning">교육용 팬텀 환경 전용입니다. 실제 환자 정보나 임상 판단에 사용하지 마세요.</p>
    <div class="grid">
      <label for="patient">환자명(가상 식별자)</label>
      <input id="patient" value="환자A" maxlength="80">
      <label for="disease">질환</label>
      <select id="disease"><option value="감기">감기</option></select>
    </div>
    <label class="confirm">
      <input id="confirmed" type="checkbox">
      <span>로봇 주변이 비어 있고 비상정지 수단을 확인했습니다.</span>
    </label>
    <button class="dry" onclick="startRun(true)">설정 검사 (로봇 미동작)</button>
    <button class="run" onclick="startRun(false)">전체 파이프라인 실행</button>
    <div id="dry-result" style="display:none; margin-top:18px;">
      <div id="dry-status">설정 검사 중</div>
      <pre id="dry-logs" style="min-height:120px;"></pre>
    </div>
  </section>
  <div id="monitor-step">
  <div class="monitor-grid">
  <section class="card">
    <h2>의료 장비 확인 화면</h2>
    <p>사전검사 또는 사후검사의 최신 프레임입니다. ACT 동작 중에는 마지막 사전검사 화면이 유지됩니다.</p>
    <img class="preview" id="object-preview" alt="Object YOLO 검사 프레임이 아직 없습니다">
    <div class="placeholder" id="object-placeholder">의료 장비 사전검사 준비 중</div>
  </section>
  <section class="card">
    <h2>의료 장비 전달 수행 화면</h2>
    <p>ACT가 사용 중인 front 카메라의 최신 화면입니다. 별도의 카메라 연결이나 YOLO 추론을 추가하지 않습니다.</p>
    <img class="preview" id="camera-preview" alt="ACT 실행이 시작되면 front 카메라가 표시됩니다">
    <div class="placeholder" id="camera-placeholder">카메라 준비 중 · ACT가 시작되면 표시됩니다.</div>
  </section>
  </div>
  <section class="card">
    <div id="status">대기 중</div>
    <pre id="logs"></pre>
    <button class="stop" onclick="stopRun()">긴급 정지 (소프트웨어)</button>
    <button class="dry" id="back-button" onclick="backToInput()">입력 화면으로 돌아가기</button>
    <p class="warning">소프트웨어 긴급 정지는 물리 비상정지 버튼을 대체하지 않습니다.</p>
  </section>
  </div>
</main>
<script>
async function startRun(dryRun) {
  const patient = document.getElementById('patient').value.trim();
  const disease = document.getElementById('disease').value;
  const confirmed = document.getElementById('confirmed').checked;
  if (!patient) return alert('가상 환자 식별자를 입력하세요.');
  if (!dryRun && !confirmed) return alert('실행 전 안전 확인 항목을 체크하세요.');
  if (!dryRun && !confirm(`${patient} / ${disease}\n로봇 파이프라인을 실행할까요?`)) return;
  const response = await fetch('/start', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({patient, disease, confirmed, dry_run: dryRun})
  });
  const result = await response.json();
  if (!response.ok) return alert(result.error || '실행 요청 실패');
  if (dryRun) {
    document.getElementById('dry-result').style.display = 'block';
    document.getElementById('dry-status').textContent = '설정 검사 중';
    document.getElementById('dry-logs').textContent = '';
    refreshDryRun();
    return;
  }
  resetPreviews();
  document.getElementById('input-step').style.display = 'none';
  document.getElementById('monitor-step').style.display = 'block';
  refresh();
}
async function stopRun() {
  if (!confirm('실행 중인 로봇 파이프라인에 긴급 정지 신호를 보낼까요?')) return;
  const response = await fetch('/stop', {method: 'POST'});
  const result = await response.json();
  if (!response.ok) alert(result.error || '중지 요청 실패');
}
async function refreshDryRun() {
  const result = await (await fetch('/status')).json();
  document.getElementById('dry-status').textContent = result.running
    ? '설정 검사 중'
    : (result.exit_code === 0 ? '설정 검사 완료 · 로봇은 움직이지 않았습니다.' : `설정 검사 실패 · 종료 코드 ${result.exit_code}`);
  document.getElementById('dry-logs').textContent = result.logs;
  if (result.running) setTimeout(refreshDryRun, 300);
}
async function refresh() {
  const result = await (await fetch('/status')).json();
  document.getElementById('status').textContent = result.running
    ? '실행 중' : (result.exit_code === null ? '대기 중' : `종료 코드: ${result.exit_code}`);
  const logs = document.getElementById('logs');
  logs.textContent = result.logs;
  logs.scrollTop = logs.scrollHeight;
  document.getElementById('back-button').disabled = result.running;
  updatePreview('camera-preview', 'camera-placeholder', '/camera-preview');
  updatePreview('object-preview', 'object-placeholder', '/object-preview');
}
const previewUrls = {};
function resetPreviews() {
  for (const imageId of ['camera-preview', 'object-preview']) {
    const image = document.getElementById(imageId);
    image.removeAttribute('src');
    image.style.display = 'none';
    if (previewUrls[imageId]) {
      URL.revokeObjectURL(previewUrls[imageId]);
      delete previewUrls[imageId];
    }
  }
  document.getElementById('camera-placeholder').style.display = 'grid';
  document.getElementById('object-placeholder').style.display = 'grid';
}
async function updatePreview(imageId, placeholderId, endpoint) {
  if (document.getElementById('monitor-step').style.display !== 'block') return;
  try {
    const response = await fetch(`${endpoint}?t=${Date.now()}`, {cache: 'no-store'});
    if (!response.ok) return;
    const blob = await response.blob();
    const nextUrl = URL.createObjectURL(blob);
    const image = document.getElementById(imageId);
    image.onload = () => {
      image.style.display = 'block';
      document.getElementById(placeholderId).style.display = 'none';
      if (previewUrls[imageId]) URL.revokeObjectURL(previewUrls[imageId]);
      previewUrls[imageId] = nextUrl;
    };
    image.src = nextUrl;
  } catch (_) {
    // Keep the preparation placeholder instead of showing a broken image.
  }
}
function backToInput() {
  document.getElementById('monitor-step').style.display = 'none';
  document.getElementById('input-step').style.display = 'block';
}
setInterval(refresh, 1000);
</script></body></html>
"""


def append_log(text: str) -> None:
    with lock:
        logs = state["logs"]
        assert isinstance(logs, list)
        logs.append(text)
        if len(logs) > 3000:
            del logs[:1000]


def run_command(command: list[str]) -> None:
    try:
        process = subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        with lock:
            state["process"] = process
        assert process.stdout is not None
        for line in process.stdout:
            append_log(line)
        code = process.wait()
        append_log(f"\n프로세스 종료 코드: {code}\n")
    except Exception as exc:
        code = -1
        append_log(f"\n실행 오류: {exc}\n")
    finally:
        with lock:
            state["process"] = None
            state["running"] = False
            state["exit_code"] = code


@app.get("/")
def index():
    return render_template_string(PAGE)


@app.post("/start")
def start():
    payload = request.get_json(silent=True) or {}
    patient = str(payload.get("patient", "")).strip()
    disease = str(payload.get("disease", "")).strip()
    dry_run = payload.get("dry_run") is True
    confirmed = payload.get("confirmed") is True
    if not patient or len(patient) > 80 or "\n" in patient or "\r" in patient:
        return jsonify(error="가상 환자 식별자는 1~80자로 입력하세요."), 400
    if disease != "감기":
        return jsonify(error="현재 지원 질환은 감기뿐입니다."), 400
    if not dry_run and not confirmed:
        return jsonify(error="실행 전 안전 확인이 필요합니다."), 400

    command = [
        str(RUNNER), disease,
        "--patient", patient,
        "--checkpoint", "050000",
        "--action-steps", "100",
        "--episode-time", "30",
        "--max-retries", "1",
    ]
    if dry_run:
        command.append("--dry-run")
    with lock:
        if state["running"]:
            return jsonify(error="이미 파이프라인이 실행 중입니다."), 409
        state["running"] = True
        state["exit_code"] = None
        state["logs"] = ["$ " + " ".join(command) + "\n"]
        OBJECT_PREVIEW.unlink(missing_ok=True)
        CAMERA_PREVIEW.unlink(missing_ok=True)
    threading.Thread(target=run_command, args=(command,), daemon=True).start()
    return jsonify(ok=True)


@app.get("/status")
def status():
    with lock:
        logs = state["logs"]
        assert isinstance(logs, list)
        return jsonify(
            running=state["running"],
            exit_code=state["exit_code"],
            logs="".join(logs),
        )


@app.get("/object-preview")
def object_preview():
    if not OBJECT_PREVIEW.is_file():
        return "Object YOLO preview is not available yet", 404
    return send_file(OBJECT_PREVIEW, mimetype="image/jpeg", max_age=0)


@app.get("/camera-preview")
def camera_preview():
    if not CAMERA_PREVIEW.is_file():
        return "ACT camera preview is not available yet", 404
    return send_file(CAMERA_PREVIEW, mimetype="image/jpeg", max_age=0)


@app.post("/stop")
def stop():
    with lock:
        process = state["process"]
    if not isinstance(process, subprocess.Popen) or process.poll() is not None:
        return jsonify(error="실행 중인 파이프라인이 없습니다."), 409
    os.killpg(process.pid, signal.SIGINT)
    append_log("\n소프트웨어 긴급 정지(SIGINT) 신호를 전체 파이프라인에 전송했습니다.\n")
    return jsonify(ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost"}:
        raise SystemExit("For robot safety, --host must remain 127.0.0.1 or localhost")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{args.port}")).start()
    app.run(host=args.host, port=args.port, debug=False, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
