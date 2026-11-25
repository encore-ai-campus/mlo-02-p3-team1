extends Control
## 최종 도전 (CHALLENGE01_CodeBot): 판테온 야외 실험장 디오라마 + NODEVERSE Python Code Studio.
## 시안(Pantheon Courtyard + Modular 3D-to-2D Sprites + Wood/Brass/Parchment Studio) 100% 반영 버전.

const Levels = preload("res://scripts/minigames/final_challenge_levels.gd")
const VM = preload("res://scripts/minigames/python_mini_vm.gd")
const Catalog = preload("res://scripts/learning_catalog.gd")

const INK := Color("1e1b18")
const INK_SOFT := Color("4a3b2c")
const PAPER := Color("f5e6c8")
const WOOD_LIGHT := Color("c88b4b")
const WOOD_MID := Color("9e642e")
const WOOD_DARK := Color("5e3716")
const BRASS := Color("f2c14e")
const NAVY := Color("182438")
const BLUE := Color("2563eb")
const GOLD := Color("f7cb54")
const GREEN := Color("2ea043")
const RED := Color("d64545")
const CYAN := Color("5fd6ff")
const PURPLE := Color("c792ea")

const SPEEDS: Array[float] = [1.0, 2.0, 4.0]
const BASE_STEP_SEC := 0.42
const TEX_DIR := "res://textures/final_challenge/"

# ---------- 진행 상태 ----------
var level_idx := 0
var attempts := 0
var hints_used := 0
var hint_step := 0
var level_cleared := false
var cleared_levels: Dictionary = {}
var total_stars := 0

# ---------- 스테이지 시각화 상태 ----------
var mode := "stack_reverse"
var slots_state: Array = []
var stack_state: Array = []
var output_state: Array = []
var rows_state: Array = []
var row_status: Dictionary = {}
var result_rows: Array = []
var active_indices: Array[int] = []
var active_row := -1
var found_index := -1
var reported_value = null
var carried_label := ""              # 로봇이 손에 들고 있는 상자 값 표시

var exec_steps: Array = []
var playback_idx := 0
var playing := false
var speed_idx := 0
var active_line := -1
var error_line := -1
var current_vars: Dictionary = {}
var last_log := "빈칸을 채우고 [▶ 실행]을 눌러 로봇을 움직여 보세요!"
var last_log_color := Color("fff2b8")
var _play_timer := 0.0
var _floating_text := ""
var _floating_color := CYAN
var _floating_timer := 0.0
var _robot_visual_pos := Vector2(210, 360)
var _robot_hop := 0.0
var _robot_flip := false
var _robot_tween: Tween
var _last_sim_result: Dictionary = {}

# ---------- 텍스처 & 폰트 ----------
var _tex: Dictionary = {}
var _code_font: Font
var _ui_font: Font
var _robot_tex: Texture2D

# ---------- UI 참조 ----------
var _stage_canvas: Control
var _goal_label: Label
var _level_badge: Label
var _domain_badge: Label
var _log_action_label: Label
var _vars_label: Label
var _api_label: Label
var _code_rows_box: VBoxContainer
var _choices_flow: HFlowContainer
var _level_tab_btns: Array[Button] = []
var _run_btn: Button
var _step_btn: Button
var _speed_btn: Button
var _hint_banner: PanelContainer
var _hint_label: Label
var _clear_overlay: ColorRect
var _clear_title: Label
var _clear_stars: Label
var _clear_detail: Label
var _clear_next_btn: Button

var _line_rows: Array[PanelContainer] = []
var _line_arrows: Array[Label] = []
var _blank_edits: Dictionary = {}
var _blank_order: Array[int] = []
var _active_blank_id := 0


# ============================================================================
# SIMULATOR HOST (DS / ALGO / SQL / DATA — 8 Modes)
# ============================================================================

class SimHost extends RefCounted:
	var mode: String
	var slots: Array = []
	var stack: Array = []
	var queue: Array = []
	var outputs: Array = []
	var rows: Array = []
	var selected_ids: Array[int] = []
	var kept_ids: Array[int] = []
	var dropped_ids: Array[int] = []
	var swap_count := 0
	var read_count := 0
	var found_idx := -1
	var reported_val = null

	func _init(lv: Dictionary) -> void:
		mode = str(lv.mode)
		if lv.has("slots"):
			slots = lv.slots.duplicate(true)
		if lv.has("rows"):
			rows = lv.rows.duplicate(true)

	func sim_call(fname: String, args: Array) -> Dictionary:
		match fname:
			"get":
				if args.size() != 1:
					return {"ok": false, "error": "get(인덱스)는 인자 1개가 필요합니다."}
				var idx := int(args[0])
				if mode == "data_clean":
					return _read_row_field(idx, "value", "값")
				if idx < 0 or idx >= slots.size():
					return {"ok": false, "error": "인덱스 %d 가 범위(0~%d)를 벗어났습니다." % [idx, slots.size() - 1]}
				read_count += 1
				var v = slots[idx]
				return {
					"ok": true,
					"value": v,
					"action": {"type": "read_slot", "idx": idx, "val": v, "msg": "GET [%d] → %s" % [idx, str(v)], "badge": "GET %s" % str(v)},
				}

			"push":
				if args.size() != 1:
					return {"ok": false, "error": "push(값)는 인자 1개가 필요합니다."}
				var v = args[0]
				stack.append(v)
				return {
					"ok": true,
					"value": null,
					"action": {"type": "push", "val": v, "list": stack.duplicate(), "msg": "PUSH %s" % str(v), "badge": "PUSH %s" % str(v)},
				}

			"pop":
				if stack.is_empty():
					return {"ok": false, "error": "스택이 비어 있어 pop() 할 수 없습니다!"}
				var v = stack.pop_back()
				return {
					"ok": true,
					"value": v,
					"action": {"type": "pop", "val": v, "list": stack.duplicate(), "msg": "POP → %s" % str(v), "badge": "POP %s" % str(v)},
				}

			"enqueue":
				if args.size() != 1:
					return {"ok": false, "error": "enqueue(값)는 인자 1개가 필요합니다."}
				var v = args[0]
				queue.append(v)
				return {
					"ok": true,
					"value": null,
					"action": {"type": "enqueue", "val": v, "list": queue.duplicate(), "msg": "ENQUEUE %s" % str(v), "badge": "ENQ %s" % str(v)},
				}

			"dequeue":
				if queue.is_empty():
					return {"ok": false, "error": "큐가 비어 있어 dequeue() 할 수 없습니다!"}
				var v = queue.pop_front()
				return {
					"ok": true,
					"value": v,
					"action": {"type": "dequeue", "val": v, "list": queue.duplicate(), "msg": "DEQUEUE → %s" % str(v), "badge": "DEQ %s" % str(v)},
				}

			"output":
				if args.size() != 1:
					return {"ok": false, "error": "output(값)는 인자 1개가 필요합니다."}
				var v = args[0]
				outputs.append(v)
				return {
					"ok": true,
					"value": null,
					"action": {"type": "output", "val": v, "outputs": outputs.duplicate(), "msg": "OUTPUT %s" % str(v), "badge": "배치 %s" % str(v)},
				}

			"swap":
				if args.size() != 2:
					return {"ok": false, "error": "swap(a, b)는 인덱스 2개가 필요합니다."}
				var a := int(args[0])
				var b := int(args[1])
				if a < 0 or a >= slots.size() or b < 0 or b >= slots.size():
					return {"ok": false, "error": "swap(%d, %d) 인덱스가 범위를 벗어났습니다." % [a, b]}
				var tmp = slots[a]
				slots[a] = slots[b]
				slots[b] = tmp
				swap_count += 1
				return {
					"ok": true,
					"value": null,
					"action": {"type": "swap", "a": a, "b": b, "slots": slots.duplicate(), "msg": "SWAP [%d] ↔ [%d]" % [a, b], "badge": "SWAP!"},
				}

			"found":
				if args.size() != 1:
					return {"ok": false, "error": "found(인덱스)는 인자 1개가 필요합니다."}
				found_idx = int(args[0])
				return {
					"ok": true,
					"value": null,
					"action": {"type": "found", "idx": found_idx, "msg": "FOUND [%d]" % found_idx, "badge": "FOUND [%d]" % found_idx},
				}

			"dept":
				if args.size() != 1:
					return {"ok": false, "error": "dept(행번호)는 인자 1개가 필요합니다."}
				return _read_row_field(int(args[0]), "dept", "부서")

			"score":
				if args.size() != 1:
					return {"ok": false, "error": "score(행번호)는 인자 1개가 필요합니다."}
				return _read_row_field(int(args[0]), "score", "점수")

			"region":
				if args.size() != 1:
					return {"ok": false, "error": "region(행번호)는 인자 1개가 필요합니다."}
				return _read_row_field(int(args[0]), "region", "지역")

			"amount":
				if args.size() != 1:
					return {"ok": false, "error": "amount(행번호)는 인자 1개가 필요합니다."}
				return _read_row_field(int(args[0]), "amount", "금액")

			"value":
				if args.size() != 1:
					return {"ok": false, "error": "value(행번호)는 인자 1개가 필요합니다."}
				return _read_row_field(int(args[0]), "value", "값")

			"is_null":
				if args.size() != 1:
					return {"ok": false, "error": "is_null(행번호)는 인자 1개가 필요합니다."}
				var i := int(args[0])
				if i < 0 or i >= rows.size():
					return {"ok": false, "error": "행 번호 %d 가 범위를 벗어났습니다." % i}
				var key := "amount" if mode == "sql_sum" else ("score" if mode == "sql_filter" else "value")
				var v = rows[i].get(key, null)
				var is_n := (v == null)
				return {
					"ok": true,
					"value": is_n,
					"action": {"type": "scan_row", "row": i, "msg": "ROW %d → %s" % [i, "NULL" if is_n else str(v)], "badge": "NULL!" if is_n else "값:%s" % str(v)},
				}

			"select_row":
				if args.size() != 1:
					return {"ok": false, "error": "select_row(행번호)는 인자 1개가 필요합니다."}
				var i := int(args[0])
				if i < 0 or i >= rows.size():
					return {"ok": false, "error": "행 번호 %d 가 범위를 벗어났습니다." % i}
				var rid := int(rows[i].id)
				if not (rid in selected_ids):
					selected_ids.append(rid)
				return {
					"ok": true,
					"value": null,
					"action": {"type": "select_row", "row": i, "record": rows[i].duplicate(), "msg": "SELECT %s (%s점)" % [str(rows[i].get("name", "")), str(rows[i].get("score", "NULL"))], "badge": "SELECT ✓"},
				}

			"drop_row":
				if args.size() != 1:
					return {"ok": false, "error": "drop_row(행번호)는 인자 1개가 필요합니다."}
				var i := int(args[0])
				if i < 0 or i >= rows.size():
					return {"ok": false, "error": "행 번호 %d 가 범위를 벗어났습니다." % i}
				var rid := int(rows[i].id)
				if not (rid in dropped_ids):
					dropped_ids.append(rid)
				return {
					"ok": true,
					"value": null,
					"action": {"type": "drop_row", "row": i, "msg": "DROP ROW %d (ID %d)" % [i, rid], "badge": "DROP ✕"},
				}

			"keep_row":
				if args.size() != 1:
					return {"ok": false, "error": "keep_row(행번호)는 인자 1개가 필요합니다."}
				var i := int(args[0])
				if i < 0 or i >= rows.size():
					return {"ok": false, "error": "행 번호 %d 가 범위를 벗어났습니다." % i}
				var rid := int(rows[i].id)
				if not (rid in kept_ids):
					kept_ids.append(rid)
				return {
					"ok": true,
					"value": null,
					"action": {"type": "keep_row", "row": i, "record": rows[i].duplicate(), "msg": "KEEP ROW %d (ID %d)" % [i, rid], "badge": "KEEP ✓"},
				}

			"report_sum":
				if args.size() != 1:
					return {"ok": false, "error": "report_sum(합계)는 인자 1개가 필요합니다."}
				reported_val = int(args[0])
				return {
					"ok": true,
					"value": null,
					"action": {"type": "report", "val": reported_val, "msg": "SUM = %d 보고!" % reported_val, "badge": "SUM=%d" % reported_val},
				}

			"report_mean":
				if args.size() != 1:
					return {"ok": false, "error": "report_mean(평균)은 인자 1개가 필요합니다."}
				reported_val = int(args[0])
				return {
					"ok": true,
					"value": null,
					"action": {"type": "report", "val": reported_val, "msg": "평균 = %d 보고!" % reported_val, "badge": "평균=%d" % reported_val},
				}

		return {"ok": false, "error": "지원하지 않는 명령어입니다: %s()" % fname}

	func _read_row_field(i: int, key: String, kor: String) -> Dictionary:
		if i < 0 or i >= rows.size():
			return {"ok": false, "error": "행 번호 %d 가 범위를 벗어났습니다." % i}
		var v = rows[i].get(key, null)
		var txt := "NULL" if v == null else str(v)
		return {
			"ok": true,
			"value": v,
			"action": {"type": "scan_row", "row": i, "msg": "%s[%d] = %s" % [kor, i, txt], "badge": "%s:%s" % [kor, txt]},
		}


## 헤드리스 테스트 및 실행 검증용 정적 시뮬레이션 헬퍼
static func simulate_level(lv_idx: int, blank_values: Dictionary) -> Dictionary:
	var lv: Dictionary = Levels.LEVELS[lv_idx]
	var src := assemble_source(lv, blank_values)
	var host := SimHost.new(lv)
	var res := VM.execute(src, host, int(lv.get("max_steps", 200)))
	var goal_res := evaluate_goal(lv, host)
	return {
		"source": src,
		"vm": res,
		"goal": goal_res,
		"cleared": res.ok and goal_res.ok,
	}


static func assemble_source(lv: Dictionary, blank_values: Dictionary) -> String:
	var out: PackedStringArray = []
	for line in lv.code_lines:
		var s: String = str(line)
		for b in lv.blanks:
			var bid: int = int(b.id)
			var token := "{{%d}}" % bid
			if s.contains(token):
				var val := str(blank_values.get(bid, "")).strip_edges()
				s = s.replace(token, val if val != "" else "___%d___" % (bid + 1))
		out.append(s)
	return "\n".join(out)


static func evaluate_goal(lv: Dictionary, host: SimHost) -> Dictionary:
	match str(lv.mode):
		"stack_reverse":
			var target: Array = lv.target
			if host.outputs == target and host.stack.is_empty():
				return {"ok": true, "reason": "스택(LIFO)으로 %s 역순 복구 완료!" % str(target)}
			if not host.stack.is_empty():
				return {"ok": false, "reason": "스택에 상자가 남아 있습니다. pop()으로 모두 꺼내 배치하세요!"}
			return {"ok": false, "reason": "작업대 결과가 목표와 다릅니다. (현재: %s / 목표: %s)" % [str(host.outputs), str(target)]}

		"queue_fifo":
			var target: Array = lv.target
			if not host.stack.is_empty():
				return {"ok": false, "reason": "스택이 아니라 큐(enqueue / dequeue)를 사용해야 접수 순서가 유지됩니다!"}
			if host.outputs == target and host.queue.is_empty():
				return {"ok": true, "reason": "큐(FIFO)로 접수 순서 %s 처리 완료!" % str(target)}
			return {"ok": false, "reason": "창구 처리 순서가 목표와 다릅니다. (현재: %s / 목표: %s)" % [str(host.outputs), str(target)]}

		"bubble_sort":
			var target: Array = lv.target
			if host.slots == target:
				return {"ok": true, "reason": "오름차순 정렬 완료! (교환 %d회)" % host.swap_count}
			return {"ok": false, "reason": "아직 오름차순이 아닙니다. (현재: %s / 목표: %s)" % [str(host.slots), str(target)]}

		"binary_search":
			var want_idx := int(lv.target_idx)
			var max_r := int(lv.get("max_reads", 6))
			if host.found_idx != want_idx:
				if host.found_idx == int(lv.target_val):
					return {"ok": false, "reason": "값(%d)이 아니라 위치 인덱스(mid = %d)를 found(mid)로 보고해야 합니다!" % [host.found_idx, want_idx]}
				return {"ok": false, "reason": "목표 인덱스(%d)를 아직 찾지 못했습니다. (현재 보고: %s)" % [want_idx, "없음" if host.found_idx < 0 else str(host.found_idx)]}
			if host.read_count > max_r:
				return {"ok": false, "reason": "조회 횟수(%d회)가 너무 많습니다! (low + high) // 2 로 절반씩 좁히세요." % host.read_count}
			return {"ok": true, "reason": "이진 탐색으로 단 %d회 조회 만에 [%d]번 칸(34) 발견!" % [host.read_count, want_idx]}

		"sql_filter":
			var target_ids: Array = lv.target_ids
			if host.selected_ids == target_ids:
				return {"ok": true, "reason": "개발팀 80점 이상 장학생 %d명 조회 완료!" % target_ids.size()}
			if host.selected_ids.size() < target_ids.size():
				return {"ok": false, "reason": "조건에 맞는 학생이 누락되었습니다. (>= 80 인지 확인하세요!)"}
			return {"ok": false, "reason": "조건에 맞지 않는 학생이 포함되었습니다. (dept=='개발' and score>=80)"}

		"sql_sum":
			var want_sum := int(lv.target_sum)
			if host.reported_val == null:
				return {"ok": false, "reason": "반복문 종료 후 report_sum(total)으로 합계를 보고해 주세요!"}
			if int(host.reported_val) == want_sum:
				return {"ok": true, "reason": "서울 지역 유효 매출 합계 SUM = %d 정확히 집계 완료!" % want_sum}
			return {"ok": false, "reason": "보고된 합계(%s)가 목표(%d)와 다릅니다. 서울 지역만 더했는지 확인하세요!" % [str(host.reported_val), want_sum]}

		"data_clean":
			var want_keep: Array = lv.target_keep_ids
			var want_drop: Array = lv.target_drop_ids
			if host.kept_ids == want_keep and host.dropped_ids == want_drop:
				return {"ok": true, "reason": "결측·이상치 %d건 제거, 정상 데이터 %d건 정제 완료!" % [want_drop.size(), want_keep.size()]}
			return {"ok": false, "reason": "정제 결과가 목표와 다릅니다. (보존 ID: %s / 제거 ID: %s)" % [str(host.kept_ids), str(host.dropped_ids)]}

		"data_mean":
			var want_mean := int(lv.target_mean)
			if host.reported_val == null:
				return {"ok": false, "reason": "반복문 종료 후 report_mean(...)으로 평균을 보고해 주세요!"}
			if int(host.reported_val) == want_mean:
				return {"ok": true, "reason": "이상치(100) 제외 대표 평균 = %d 정확히 산출 완료!" % want_mean}
			if int(host.reported_val) == 10:
				return {"ok": false, "reason": "전체 개수(5)가 아니라 정상 데이터 개수(cnt=4)로 나누어야 합니다!"}
			return {"ok": false, "reason": "보고된 평균(%s)이 목표(%d)와 다릅니다. 이상치 제외 조건(v < 80)과 나눗셈을 확인하세요!" % [str(host.reported_val), want_mean]}

	return {"ok": false, "reason": "알 수 없는 스테이지 모드"}


# ============================================================================
# LIFECYCLE & TEXTURE LOADING
# ============================================================================

func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	_ui_font = load("res://fonts/NotoSansKR_Medium.tres")
	_robot_tex = load("res://textures/sprites/robot.png")
	var f := SystemFont.new()
	f.font_names = PackedStringArray(["D2Coding", "Consolas", "Cascadia Mono", "Malgun Gothic"])
	_code_font = f
	_load_textures()
	_build_ui()
	_telemetry("start_task", [Levels.STAGE_ID, {"title": Levels.STAGE_TITLE, "total_levels": Levels.LEVELS.size(), "mode": "code_bot"}])
	_load_level(0)


func _load_textures() -> void:
	var keys: Array[String] = [
		"pantheon_stage_bg",
		"slot_normal", "slot_active",
		"crate_blue", "crate_gold", "crate_red", "cube_null",
		"stack_tower", "queue_belt", "output_bench", "crystal_gauge",
		"row_normal", "row_green", "row_red",
		"code_frame", "blank_slot", "chip_parchment",
		"btn_green", "btn_blue", "btn_purple", "btn_brown",
	]
	for k: String in keys:
		var path: String = TEX_DIR + k + ".png"
		if ResourceLoader.exists(path):
			_tex[k] = load(path)


func _tex_box(key: String, m_lr := 18.0, m_tb := 16.0, pad_lr := 12.0, pad_tb := 6.0, modulate := Color.WHITE) -> StyleBox:
	if _tex.has(key) and _tex[key] != null:
		var st := StyleBoxTexture.new()
		st.texture = _tex[key]
		st.texture_margin_left = m_lr
		st.texture_margin_right = m_lr
		st.texture_margin_top = m_tb
		st.texture_margin_bottom = m_tb
		st.content_margin_left = pad_lr
		st.content_margin_right = pad_lr
		st.content_margin_top = pad_tb
		st.content_margin_bottom = pad_tb
		st.modulate_color = modulate
		return st
	return _flat_box(WOOD_MID, WOOD_DARK, 3, 8, int(pad_lr))


func _flat_box(bg: Color, border := WOOD_DARK, bw := 3, radius := 8, pad := 10, shadow := false) -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = bg
	sb.border_color = border
	sb.set_border_width_all(bw)
	sb.set_corner_radius_all(radius)
	sb.content_margin_left = pad
	sb.content_margin_right = pad
	sb.content_margin_top = maxi(2, pad - 3)
	sb.content_margin_bottom = maxi(2, pad - 3)
	if shadow:
		sb.shadow_color = Color(0, 0, 0, 0.38)
		sb.shadow_size = 8
		sb.shadow_offset = Vector2(0, 4)
	return sb


func _mk_label(t: String, sz: int, col: Color, mono := false, outline_sz := 0, outline_col := INK) -> Label:
	var l := Label.new()
	l.text = t
	l.add_theme_font_size_override("font_size", sz)
	l.add_theme_color_override("font_color", col)
	if mono:
		l.add_theme_font_override("font", _code_font)
	if outline_sz > 0:
		l.add_theme_constant_override("outline_size", outline_sz)
		l.add_theme_color_override("font_outline_color", outline_col)
	return l


func _mk_gem_btn(t: String, tex_key: String, min_sz: Vector2, sz := 18) -> Button:
	var b := Button.new()
	b.text = t
	b.custom_minimum_size = min_sz
	b.add_theme_font_size_override("font_size", sz)
	b.add_theme_color_override("font_color", Color.WHITE)
	b.add_theme_color_override("font_hover_color", Color("fff8dc"))
	b.add_theme_constant_override("outline_size", 4)
	b.add_theme_color_override("font_outline_color", Color(0.08, 0.08, 0.12, 0.9))
	b.add_theme_stylebox_override("normal", _tex_box(tex_key, 18, 18, 8, 6, Color.WHITE))
	b.add_theme_stylebox_override("hover", _tex_box(tex_key, 18, 18, 8, 6, Color(1.12, 1.12, 1.12)))
	b.add_theme_stylebox_override("pressed", _tex_box(tex_key, 18, 18, 8, 6, Color(0.86, 0.86, 0.86)))
	b.add_theme_stylebox_override("focus", _tex_box(tex_key, 18, 18, 8, 6, Color(1.08, 1.08, 1.08)))
	return b


func _mk_top_dark_btn(t: String, min_sz: Vector2, sz := 13) -> Button:
	var b := Button.new()
	b.text = t
	b.custom_minimum_size = min_sz
	b.add_theme_font_size_override("font_size", sz)
	b.add_theme_color_override("font_color", Color("f8f1dc"))
	b.add_theme_color_override("font_hover_color", GOLD)
	b.add_theme_stylebox_override("normal", _tex_box("row_normal", 32, 14, 16, 4))
	b.add_theme_stylebox_override("hover", _tex_box("row_normal", 32, 14, 16, 4, Color(1.15, 1.15, 1.15)))
	b.add_theme_stylebox_override("pressed", _tex_box("row_normal", 32, 14, 16, 4, Color(0.88, 0.88, 0.88)))
	b.add_theme_stylebox_override("focus", _tex_box("row_normal", 32, 14, 16, 4))
	return b


func _mk_parchment_chip(t: String, min_sz: Vector2, sz := 14, mono := true) -> Button:
	var b := Button.new()
	b.text = t
	b.custom_minimum_size = min_sz
	if mono:
		b.add_theme_font_override("font", _code_font)
	b.add_theme_font_size_override("font_size", sz)
	b.add_theme_color_override("font_color", INK)
	b.add_theme_color_override("font_hover_color", Color("0f172a"))
	b.add_theme_stylebox_override("normal", _tex_box("chip_parchment", 14, 14, 12, 5))
	b.add_theme_stylebox_override("hover", _tex_box("chip_parchment", 14, 14, 12, 5, Color(1.06, 1.04, 0.96)))
	b.add_theme_stylebox_override("pressed", _tex_box("chip_parchment", 14, 14, 12, 5, Color(0.92, 0.88, 0.80)))
	b.add_theme_stylebox_override("focus", _tex_box("chip_parchment", 14, 14, 12, 5))
	return b


# ============================================================================
# UI LAYOUT CONSTRUCTION (1280x720 — Matches Mockup 1:1)
# ============================================================================

func _build_ui() -> void:
	# 1) 풀스크린 판테온 신전 코트야드 & 바다 배경
	if _tex.has("pantheon_stage_bg"):
		var bg_rect := TextureRect.new()
		bg_rect.texture = _tex["pantheon_stage_bg"]
		bg_rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		bg_rect.stretch_mode = TextureRect.STRETCH_SCALE
		bg_rect.set_anchors_preset(Control.PRESET_FULL_RECT)
		bg_rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
		add_child(bg_rect)
	else:
		var bg := ColorRect.new()
		bg.color = Color("0d5c75")
		bg.set_anchors_preset(Control.PRESET_FULL_RECT)
		add_child(bg)

	# 2) 왼쪽 스테이지 드로잉 캔버스 (배경 코트야드 위에 오브젝트와 로봇을 직접 렌더링)
	_stage_canvas = Control.new()
	_stage_canvas.position = Vector2(0, 0)
	_stage_canvas.size = Vector2(752, 720)
	_stage_canvas.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_stage_canvas.draw.connect(_draw_stage)
	add_child(_stage_canvas)

	# 3) 상단 플로팅 HUD 바 (y: 8..50)
	var top_bar := HBoxContainer.new()
	top_bar.position = Vector2(10, 7)
	top_bar.size = Vector2(1260, 42)
	top_bar.add_theme_constant_override("separation", 6)
	add_child(top_bar)

	# 분야 배지 (파란 보석 배지)
	var dom_p := PanelContainer.new()
	dom_p.add_theme_stylebox_override("panel", _tex_box("btn_blue", 16, 16, 12, 4))
	_domain_badge = _mk_label("❖ 자료구조", 15, Color.WHITE, false, 3, NAVY)
	dom_p.add_child(_domain_badge)
	top_bar.add_child(dom_p)

	# Lv 카운터 배지 (브라운 배지)
	var lv_p := PanelContainer.new()
	lv_p.add_theme_stylebox_override("panel", _tex_box("btn_brown", 16, 16, 10, 4))
	_level_badge = _mk_label("Lv 1/8", 15, Color.WHITE, false, 3, INK)
	lv_p.add_child(_level_badge)
	top_bar.add_child(lv_p)

	# 1~8 시나리오 숫자 버튼
	var tabs_h := HBoxContainer.new()
	tabs_h.add_theme_constant_override("separation", 3)
	for i in Levels.LEVELS.size():
		var tb := Button.new()
		tb.text = str(i + 1)
		tb.custom_minimum_size = Vector2(32, 34)
		tb.add_theme_font_size_override("font_size", 15)
		var target_i := i
		tb.pressed.connect(func(): _load_level(target_i))
		tabs_h.add_child(tb)
		_level_tab_btns.append(tb)
	top_bar.add_child(tabs_h)

	# 중앙 양피지 목표 배너
	var goal_p := PanelContainer.new()
	goal_p.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	goal_p.add_theme_stylebox_override("panel", _tex_box("chip_parchment", 16, 14, 14, 4))
	var gh := HBoxContainer.new()
	gh.add_theme_constant_override("separation", 6)
	gh.add_child(_mk_label("●", 14, RED))
	_goal_label = _mk_label("", 14, INK)
	_goal_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_goal_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	gh.add_child(_goal_label)
	goal_p.add_child(gh)
	top_bar.add_child(goal_p)

	# 우측 상단 버튼 3종: 힌트 / 목록 / 3D 월드
	var hint_btn := _mk_top_dark_btn("★ 힌트(F)", Vector2(104, 38), 13)
	hint_btn.pressed.connect(_show_next_hint)
	top_bar.add_child(hint_btn)

	var menu_btn := _mk_top_dark_btn("≡ 목록", Vector2(86, 38), 13)
	menu_btn.pressed.connect(_exit_to_menu)
	top_bar.add_child(menu_btn)

	var exit_btn := _mk_top_dark_btn("◀ 3D 월드", Vector2(114, 38), 13)
	exit_btn.pressed.connect(_exit_to_world)
	top_bar.add_child(exit_btn)

	# 4) 왼쪽 하단 플로팅 동작 로그 & 실시간 변수 바 (시안 좌하단 그대로!)
	var log_bar := PanelContainer.new()
	log_bar.position = Vector2(12, 666)
	log_bar.size = Vector2(724, 46)
	log_bar.add_theme_stylebox_override("panel", _tex_box("row_normal", 34, 16, 26, 6))
	add_child(log_bar)

	var log_h := HBoxContainer.new()
	log_h.add_theme_constant_override("separation", 10)
	log_bar.add_child(log_h)

	log_h.add_child(_mk_label("▶ 동작 로그  |", 14, Color("e2e8f0")))
	_log_action_label = _mk_label("대기 중", 15, GOLD)
	_log_action_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_log_action_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	log_h.add_child(_log_action_label)

	log_h.add_child(_mk_label("|", 14, Color("94a3b8")))
	_vars_label = _mk_label("변수: -", 14, Color("f8fafc"), true)
	log_h.add_child(_vars_label)

	# 힌트 말풍선 배너 (로그 바 바로 위 플로팅)
	_hint_banner = PanelContainer.new()
	_hint_banner.position = Vector2(24, 610)
	_hint_banner.size = Vector2(700, 50)
	_hint_banner.visible = false
	_hint_banner.add_theme_stylebox_override("panel", _tex_box("chip_parchment", 16, 14, 14, 6))
	_hint_label = _mk_label("", 14, INK)
	_hint_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_hint_banner.add_child(_hint_label)
	add_child(_hint_banner)

	# 5) 오른쪽: NODEVERSE · Python Code Studio (원목 & 황동 프레임 스튜디오)
	var studio_outer := PanelContainer.new()
	studio_outer.position = Vector2(748, 56)
	studio_outer.size = Vector2(520, 656)
	studio_outer.add_theme_stylebox_override("panel", _flat_box(WOOD_LIGHT, WOOD_DARK, 4, 12, 12, true))
	add_child(studio_outer)

	var studio_inner := PanelContainer.new()
	studio_inner.add_theme_stylebox_override("panel", _flat_box(Color("b6783d"), BRASS, 2, 9, 10))
	studio_outer.add_child(studio_inner)

	var right_v := VBoxContainer.new()
	right_v.add_theme_constant_override("separation", 8)
	studio_inner.add_child(right_v)

	# 스튜디오 상단 명패: </> NODEVERSE · Python Code Studio
	var studio_hdr := PanelContainer.new()
	studio_hdr.add_theme_stylebox_override("panel", _tex_box("chip_parchment", 16, 14, 12, 5))
	var sh_h := HBoxContainer.new()
	sh_h.add_theme_constant_override("separation", 10)
	var code_tag := PanelContainer.new()
	code_tag.add_theme_stylebox_override("panel", _tex_box("btn_blue", 12, 12, 8, 2))
	code_tag.add_child(_mk_label("</>", 14, Color.WHITE, true, 2, NAVY))
	sh_h.add_child(code_tag)
	var st_title := _mk_label("코딱지 · Python Code Studio", 17, INK)
	st_title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	sh_h.add_child(st_title)
	studio_hdr.add_child(sh_h)
	right_v.add_child(studio_hdr)

	# 칠판형 Python 코드 편집기 (code_frame.png 9-slice)
	var blackboard := PanelContainer.new()
	blackboard.size_flags_vertical = Control.SIZE_EXPAND_FILL
	blackboard.custom_minimum_size = Vector2(484, 326)
	blackboard.add_theme_stylebox_override("panel", _tex_box("code_frame", 26, 24, 24, 18))
	right_v.add_child(blackboard)

	var bb_v := VBoxContainer.new()
	bb_v.add_theme_constant_override("separation", 4)
	blackboard.add_child(bb_v)

	_api_label = _mk_label("", 11, Color("86efac"), true)
	_api_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	bb_v.add_child(_api_label)

	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_code_rows_box = VBoxContainer.new()
	_code_rows_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_code_rows_box.add_theme_constant_override("separation", 2)
	scroll.add_child(_code_rows_box)
	bb_v.add_child(scroll)

	# 양피지 '예시 코드 보기' 트레이
	var tray_p := PanelContainer.new()
	tray_p.custom_minimum_size = Vector2(484, 152)
	tray_p.add_theme_stylebox_override("panel", _flat_box(Color("ebd7b2"), WOOD_DARK, 3, 8, 10))
	right_v.add_child(tray_p)

	var tray_v := VBoxContainer.new()
	tray_v.add_theme_constant_override("separation", 6)
	tray_p.add_child(tray_v)

	var tray_hdr := HBoxContainer.new()
	var ribbon := PanelContainer.new()
	ribbon.add_theme_stylebox_override("panel", _tex_box("btn_brown", 18, 12, 16, 4))
	ribbon.add_child(_mk_label("예시 코드 보기", 13, Color.WHITE, false, 2, INK))
	tray_hdr.add_child(ribbon)

	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	tray_hdr.add_child(spacer)

	var clear_one := _mk_parchment_chip("✕ 선택 지우기", Vector2(100, 28), 12, false)
	clear_one.pressed.connect(_clear_active_blank)
	tray_hdr.add_child(clear_one)

	var clear_all := _mk_parchment_chip("✕ 모두 비우기", Vector2(100, 28), 12, false)
	clear_all.pressed.connect(_clear_all_blanks)
	tray_hdr.add_child(clear_all)
	tray_v.add_child(tray_hdr)

	_choices_flow = HFlowContainer.new()
	_choices_flow.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_choices_flow.add_theme_constant_override("h_separation", 8)
	_choices_flow.add_theme_constant_override("v_separation", 6)
	tray_v.add_child(_choices_flow)

	# 하단 4색 보석 아케이드 실행 버튼 바
	var ctrl_h := HBoxContainer.new()
	ctrl_h.add_theme_constant_override("separation", 6)
	right_v.add_child(ctrl_h)

	_run_btn = _mk_gem_btn("▶ 실행", "btn_green", Vector2(130, 56), 18)
	_run_btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_run_btn.pressed.connect(_on_run_pressed)
	ctrl_h.add_child(_run_btn)

	_step_btn = _mk_gem_btn("⏭ 한 줄", "btn_blue", Vector2(114, 56), 16)
	_step_btn.pressed.connect(_on_step_pressed)
	ctrl_h.add_child(_step_btn)

	_speed_btn = _mk_gem_btn("⏩ 1x 배속", "btn_purple", Vector2(120, 56), 15)
	_speed_btn.pressed.connect(_on_speed_pressed)
	ctrl_h.add_child(_speed_btn)

	var reset_btn := _mk_gem_btn("↻ 리셋", "btn_brown", Vector2(102, 56), 16)
	reset_btn.pressed.connect(_reset_board_only)
	ctrl_h.add_child(reset_btn)

	_build_clear_overlay()


func _build_clear_overlay() -> void:
	_clear_overlay = ColorRect.new()
	_clear_overlay.color = Color(0, 0, 0, 0.62)
	_clear_overlay.set_anchors_preset(Control.PRESET_FULL_RECT)
	_clear_overlay.visible = false
	add_child(_clear_overlay)

	var center := CenterContainer.new()
	center.set_anchors_preset(Control.PRESET_FULL_RECT)
	_clear_overlay.add_child(center)

	var outer := PanelContainer.new()
	outer.custom_minimum_size = Vector2(540, 0)
	outer.add_theme_stylebox_override("panel", _flat_box(WOOD_LIGHT, WOOD_DARK, 4, 14, 14, true))
	center.add_child(outer)

	var card := PanelContainer.new()
	card.add_theme_stylebox_override("panel", _tex_box("chip_parchment", 20, 18, 24, 20))
	outer.add_child(card)

	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 12)
	card.add_child(v)

	_clear_title = _mk_label("레벨 클리어!", 28, NAVY)
	_clear_title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	v.add_child(_clear_title)

	_clear_stars = _mk_label("★★★", 36, Color("c48a10"), false, 3, INK)
	_clear_stars.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	v.add_child(_clear_stars)

	_clear_detail = _mk_label("", 17, INK)
	_clear_detail.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_clear_detail.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(_clear_detail)

	var bh := HBoxContainer.new()
	bh.alignment = BoxContainer.ALIGNMENT_CENTER
	bh.add_theme_constant_override("separation", 12)
	var retry_b := _mk_gem_btn("↻ 다시 풀기", "btn_brown", Vector2(156, 50), 16)
	retry_b.pressed.connect(func():
		_clear_overlay.visible = false
		_reset_board_only())
	bh.add_child(retry_b)

	_clear_next_btn = _mk_gem_btn("다음 레벨 ▶", "btn_green", Vector2(210, 50), 17)
	_clear_next_btn.pressed.connect(_on_clear_next)
	bh.add_child(_clear_next_btn)
	v.add_child(bh)


# ============================================================================
# LEVEL LOADING & CODE EDITOR
# ============================================================================

func _load_level(idx: int) -> void:
	level_idx = clampi(idx, 0, Levels.LEVELS.size() - 1)
	var lv: Dictionary = Levels.LEVELS[level_idx]
	mode = str(lv.mode)
	attempts = 0
	hints_used = 0
	hint_step = 0
	level_cleared = false
	_clear_overlay.visible = false
	_hint_banner.visible = false

	_domain_badge.text = "❖ " + str(lv.domain)
	_level_badge.text = "Lv %d/%d" % [level_idx + 1, Levels.LEVELS.size()]
	_goal_label.text = str(lv.goal)
	_api_label.text = "# " + str(lv.api_help)
	_refresh_level_tabs()

	_build_code_editor(lv)
	_build_choice_chips(lv)
	_reset_board_only()
	_set_log("준비 완료 — 빈칸을 채우고 [▶ 실행]을 누르세요!", Color("fff2b8"))

	_telemetry("start_attempt", [Levels.STAGE_ID, level_idx + 1, {"level_id": lv.id, "goal": lv.goal}])


func _refresh_level_tabs() -> void:
	for i in _level_tab_btns.size():
		var b := _level_tab_btns[i]
		var is_cur := (i == level_idx)
		var is_done := cleared_levels.has(i)
		if is_cur:
			b.add_theme_color_override("font_color", Color.WHITE)
			b.add_theme_stylebox_override("normal", _tex_box("btn_blue", 10, 10, 4, 2))
			b.add_theme_stylebox_override("hover", _tex_box("btn_blue", 10, 10, 4, 2))
		elif is_done:
			b.add_theme_color_override("font_color", Color.WHITE)
			b.add_theme_stylebox_override("normal", _tex_box("btn_green", 10, 10, 4, 2))
			b.add_theme_stylebox_override("hover", _tex_box("btn_green", 10, 10, 4, 2))
		else:
			b.add_theme_color_override("font_color", INK)
			b.add_theme_stylebox_override("normal", _tex_box("chip_parchment", 10, 10, 4, 2))
			b.add_theme_stylebox_override("hover", _tex_box("chip_parchment", 10, 10, 4, 2, Color(1.06, 1.04, 0.95)))


func _build_code_editor(lv: Dictionary) -> void:
	for c in _code_rows_box.get_children():
		c.queue_free()
	_line_rows.clear()
	_line_arrows.clear()
	_blank_edits.clear()
	_blank_order.clear()

	var blank_meta := {}
	for b in lv.blanks:
		blank_meta[int(b.id)] = b
		_blank_order.append(int(b.id))

	var re := RegEx.new()
	re.compile("\\{\\{(\\d+)\\}\\}")

	for i in lv.code_lines.size():
		var raw: String = str(lv.code_lines[i])
		var row_p := PanelContainer.new()
		row_p.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row_p.add_theme_stylebox_override("panel", _flat_box(Color(0, 0, 0, 0), Color(0, 0, 0, 0), 0, 4, 2))
		var h := HBoxContainer.new()
		h.add_theme_constant_override("separation", 0)
		row_p.add_child(h)

		var arrow := _mk_label(" ", 13, GOLD, true)
		arrow.custom_minimum_size = Vector2(18, 25)
		h.add_child(arrow)
		_line_arrows.append(arrow)

		var lno := _mk_label("%2d  " % (i + 1), 13, Color("6c7f9e"), true)
		lno.custom_minimum_size = Vector2(30, 25)
		h.add_child(lno)

		var pos := 0
		var matches := re.search_all(raw)
		for m in matches:
			var m_start := m.get_start()
			var m_end := m.get_end()
			if m_start > pos:
				h.add_child(_mk_code_segment(raw.substr(pos, m_start - pos), raw.strip_edges().begins_with("#")))
			var bid := m.get_string(1).to_int()
			var binfo: Dictionary = blank_meta.get(bid, {"hint": "코드 입력", "width": 150})
			var le := _mk_blank_input(bid, binfo)
			h.add_child(le)
			_blank_edits[bid] = le
			pos = m_end
		if pos < raw.length():
			h.add_child(_mk_code_segment(raw.substr(pos), raw.strip_edges().begins_with("#")))

		_code_rows_box.add_child(row_p)
		_line_rows.append(row_p)

	if not _blank_order.is_empty():
		_select_blank(_blank_order[0])


func _mk_code_segment(seg: String, is_comment: bool) -> Label:
	var col := Color("7fbf7f") if is_comment else Color("f1f5f9")
	var trimmed := seg.strip_edges()
	if not is_comment:
		if trimmed.begins_with("for ") or trimmed.begins_with("if ") or trimmed.begins_with("else") or trimmed.begins_with("elif ") or trimmed.begins_with("while ") or trimmed == "break":
			col = PURPLE
	var l := _mk_label(seg, 14, col, true)
	l.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	return l


func _mk_blank_input(bid: int, binfo: Dictionary) -> LineEdit:
	var le := LineEdit.new()
	le.placeholder_text = "빈칸 %d" % (bid + 1)
	le.tooltip_text = str(binfo.get("hint", "코드를 입력하거나 아래 보기에서 선택"))
	le.custom_minimum_size = Vector2(float(binfo.get("width", 150)), 28)
	le.add_theme_font_override("font", _code_font)
	le.add_theme_font_size_override("font_size", 14)
	le.add_theme_color_override("font_color", Color("fff7cc"))
	le.add_theme_color_override("font_placeholder_color", Color("8094b8"))
	le.add_theme_stylebox_override("normal", _tex_box("blank_slot", 14, 12, 10, 3, Color(0.85, 0.85, 0.85)))
	le.add_theme_stylebox_override("focus", _tex_box("blank_slot", 14, 12, 10, 3, Color(1.15, 1.12, 1.0)))
	le.focus_entered.connect(func(): _select_blank(bid, false))
	le.text_submitted.connect(func(_t): _on_run_pressed())
	return le


func _select_blank(bid: int, grab := true) -> void:
	_active_blank_id = bid
	for k in _blank_edits:
		var le: LineEdit = _blank_edits[k]
		var is_sel := (int(k) == bid)
		le.add_theme_stylebox_override("normal", _tex_box(
			"blank_slot", 14, 12, 10, 3,
			Color(1.15, 1.12, 1.0) if is_sel else Color(0.75, 0.78, 0.88)
		))
	if grab and _blank_edits.has(bid):
		(_blank_edits[bid] as LineEdit).grab_focus()


func _build_choice_chips(lv: Dictionary) -> void:
	for c in _choices_flow.get_children():
		c.queue_free()
	for ch in lv.choices:
		var code_str := str(ch)
		var btn := _mk_parchment_chip(code_str, Vector2(0, 34), 14, true)
		btn.pressed.connect(func(): _insert_choice(code_str))
		_choices_flow.add_child(btn)


func _insert_choice(code_str: String) -> void:
	if playing:
		_stop_playback()
	if not _blank_edits.has(_active_blank_id):
		if _blank_order.is_empty():
			return
		_active_blank_id = _blank_order[0]
	var le: LineEdit = _blank_edits[_active_blank_id]
	le.text = code_str
	var cur_pos := _blank_order.find(_active_blank_id)
	for offset in range(1, _blank_order.size()):
		var nxt_id := _blank_order[(cur_pos + offset) % _blank_order.size()]
		var nxt_le: LineEdit = _blank_edits[nxt_id]
		if nxt_le.text.strip_edges() == "":
			_select_blank(nxt_id, false)
			return
	_select_blank(_active_blank_id, false)


func _clear_active_blank() -> void:
	if playing:
		_stop_playback()
	if _blank_edits.has(_active_blank_id):
		(_blank_edits[_active_blank_id] as LineEdit).text = ""


func _clear_all_blanks() -> void:
	if playing:
		_stop_playback()
	for k in _blank_edits:
		(_blank_edits[k] as LineEdit).text = ""
	if not _blank_order.is_empty():
		_select_blank(_blank_order[0])


# ============================================================================
# BOARD RESET & PLAYBACK
# ============================================================================

func _reset_board_only() -> void:
	_stop_playback()
	var lv: Dictionary = Levels.LEVELS[level_idx]
	slots_state = lv.slots.duplicate(true) if lv.has("slots") else []
	rows_state = lv.rows.duplicate(true) if lv.has("rows") else []
	stack_state.clear()
	output_state.clear()
	row_status.clear()
	result_rows.clear()
	active_indices.clear()
	active_row = -1
	found_index = -1
	reported_value = null
	carried_label = ""
	exec_steps.clear()
	playback_idx = 0
	active_line = -1
	error_line = -1
	current_vars.clear()
	_floating_text = ""
	_robot_visual_pos = _default_robot_pos()
	_robot_hop = 0.0
	_update_line_highlights()
	_vars_label.text = "변수: -"
	_stage_canvas.queue_redraw()


func _collect_blank_values() -> Dictionary:
	var vals := {}
	for k in _blank_edits:
		vals[int(k)] = (_blank_edits[k] as LineEdit).text
	return vals


func _prepare_execution() -> Dictionary:
	_reset_board_only()
	attempts += 1
	var sim := simulate_level(level_idx, _collect_blank_values())
	_telemetry("record_operation", ["run_code", sim.cleared, sim.vm.error if not sim.vm.ok else sim.goal.reason, {}, {}, {
		"stage": Levels.STAGE_ID,
		"level": level_idx + 1,
		"attempt": attempts,
		"steps": sim.vm.steps.size(),
	}])
	return sim


func _on_run_pressed() -> void:
	if playing:
		_stop_playback()
		_set_log("실행 일시 정지", GOLD)
		return
	var sim := _prepare_execution()
	_last_sim_result = sim
	if not sim.vm.ok and sim.vm.steps.is_empty():
		error_line = int(sim.vm.error_line)
		_update_line_highlights()
		_set_log("%d번 줄 오류: %s" % [error_line, sim.vm.error], Color("ff9e9e"))
		return
	exec_steps = sim.vm.steps
	playback_idx = 0
	playing = true
	_play_timer = 0.05
	_run_btn.text = "⏹ 정지"
	_set_log("코드 자동 실행 중...", CYAN)


func _on_step_pressed() -> void:
	if playing:
		_stop_playback()
	if exec_steps.is_empty() or playback_idx >= exec_steps.size():
		var sim := _prepare_execution()
		_last_sim_result = sim
		if not sim.vm.ok and sim.vm.steps.is_empty():
			error_line = int(sim.vm.error_line)
			_update_line_highlights()
			_set_log("%d번 줄 오류: %s" % [error_line, sim.vm.error], Color("ff9e9e"))
			return
		exec_steps = sim.vm.steps
		playback_idx = 0
	_advance_one_step()


func _on_speed_pressed() -> void:
	speed_idx = (speed_idx + 1) % SPEEDS.size()
	_speed_btn.text = "⏩ %dx 배속" % int(SPEEDS[speed_idx])


func _stop_playback() -> void:
	playing = false
	_run_btn.text = "▶ 실행"


func _process(delta: float) -> void:
	if _floating_timer > 0.0:
		_floating_timer = maxf(0.0, _floating_timer - delta)
		if _floating_timer == 0.0:
			_floating_text = ""
		_stage_canvas.queue_redraw()

	if playing:
		_play_timer -= delta
		if _play_timer <= 0.0:
			_advance_one_step()
			_play_timer = BASE_STEP_SEC / SPEEDS[speed_idx]


func _advance_one_step() -> void:
	if playback_idx >= exec_steps.size():
		_finish_playback()
		return
	var st: Dictionary = exec_steps[playback_idx]
	playback_idx += 1
	active_line = int(st.line)
	current_vars = st.vars
	_update_line_highlights()
	_update_vars_ui()

	var act: Dictionary = st.action
	var atype: String = str(act.get("type", "noop"))
	match atype:
		"read_slot":
			var idx := int(act.idx)
			active_indices = [idx]
			if mode in ["stack_reverse", "queue_fifo"]:
				carried_label = str(act.val)
			_animate_robot_to(_slot_robot_pos(idx))
			_show_float(str(act.badge), CYAN)
			_set_log(str(act.msg), CYAN)
		"push", "enqueue":
			stack_state = act.list.duplicate()
			carried_label = str(act.val)
			_animate_robot_to(_stack_robot_pos())
			_show_float(str(act.badge), CYAN)
			_set_log(str(act.msg), GOLD)
		"pop", "dequeue":
			stack_state = act.list.duplicate()
			carried_label = str(act.val)
			_animate_robot_to(_stack_robot_pos())
			_show_float(str(act.badge), GOLD)
			_set_log(str(act.msg), GOLD)
		"output":
			output_state = act.outputs.duplicate()
			carried_label = ""
			_animate_robot_to(_output_robot_pos(maxi(0, output_state.size() - 1)))
			_show_float(str(act.badge), Color("86efac"))
			_set_log(str(act.msg), Color("86efac"))
		"swap":
			var a := int(act.a)
			var b := int(act.b)
			slots_state = act.slots.duplicate()
			active_indices = [a, b]
			_animate_robot_to((_slot_robot_pos(a) + _slot_robot_pos(b)) * 0.5)
			_show_float("SWAP!", GOLD)
			_set_log(str(act.msg), GOLD)
		"found":
			found_index = int(act.idx)
			active_indices = [found_index]
			_animate_robot_to(_slot_robot_pos(found_index))
			_show_float(str(act.badge), Color("86efac"))
			_set_log(str(act.msg), Color("86efac"))
		"scan_row":
			var r := int(act.row)
			active_row = r
			_animate_robot_to(_row_robot_pos(r))
			_show_float(str(act.badge), CYAN)
			_set_log(str(act.msg), CYAN)
		"select_row":
			var r := int(act.row)
			active_row = r
			row_status[r] = "selected"
			result_rows.append(act.record)
			_animate_robot_to(_row_robot_pos(r))
			_show_float("SELECT ✓", Color("86efac"))
			_set_log(str(act.msg), Color("86efac"))
		"keep_row":
			var r := int(act.row)
			active_row = r
			row_status[r] = "kept"
			result_rows.append(act.record)
			_animate_robot_to(_row_robot_pos(r))
			_show_float("KEEP ✓", Color("86efac"))
			_set_log(str(act.msg), Color("86efac"))
		"drop_row":
			var r := int(act.row)
			active_row = r
			row_status[r] = "dropped"
			_animate_robot_to(_row_robot_pos(r))
			_show_float("DROP ✕", Color("fca5a5"))
			_set_log(str(act.msg), Color("fca5a5"))
		"report":
			reported_value = act.val
			_show_float(str(act.badge), GOLD)
			_set_log(str(act.msg), GOLD)

	_stage_canvas.queue_redraw()

	if playback_idx >= exec_steps.size():
		if playing:
			playing = false
			_run_btn.text = "▶ 실행"
			get_tree().create_timer(0.35 / SPEEDS[speed_idx]).timeout.connect(_finish_playback)
		else:
			_finish_playback()


func _finish_playback() -> void:
	_stop_playback()
	carried_label = ""
	_stage_canvas.queue_redraw()
	if _last_sim_result.is_empty():
		return
	var vm_res: Dictionary = _last_sim_result.vm
	if not vm_res.ok:
		error_line = int(vm_res.error_line)
		_update_line_highlights()
		_set_log("%d번 줄 오류: %s" % [error_line, vm_res.error], Color("fca5a5"))
		return
	var goal_res: Dictionary = _last_sim_result.goal
	if goal_res.ok:
		_on_level_cleared(str(goal_res.reason))
	else:
		_set_log("미달성: %s" % str(goal_res.reason), GOLD)


func _on_level_cleared(reason: String) -> void:
	level_cleared = true
	cleared_levels[level_idx] = true
	_refresh_level_tabs()
	var stars := 3 if (attempts <= 2 and hints_used == 0) else (2 if attempts <= 4 else 1)
	total_stars += stars
	var is_last := level_idx >= Levels.LEVELS.size() - 1

	_set_log("🎉 " + reason, Color("86efac"))
	_clear_title.text = "🏆 8대 분야 자동화 완전 정복!" if is_last else "🎉 레벨 %d 클리어!" % (level_idx + 1)
	_clear_stars.text = "★".repeat(stars) + "☆".repeat(3 - stars)
	_clear_detail.text = "%s\n실행 횟수: %d회 · 총 스텝: %d" % [reason, attempts, exec_steps.size()]
	_clear_next_btn.text = "3D 월드로 복귀 ▶" if is_last else "다음 레벨 ▶"
	_clear_overlay.visible = true

	_telemetry("complete_attempt", [Levels.STAGE_ID, true, "", {"level": level_idx + 1, "attempts": attempts, "hints": hints_used, "stars": stars}])
	if is_last or cleared_levels.size() >= Levels.LEVELS.size():
		var avg_stars := clampi(roundi(float(total_stars) / float(maxi(cleared_levels.size(), 1))), 1, 3)
		_telemetry("complete_task", [Levels.STAGE_ID, {"levels": Levels.LEVELS.size(), "stars": avg_stars}])
		MiniGameBase.record_clear(Levels.STAGE_ID, avg_stars)


func _on_clear_next() -> void:
	_clear_overlay.visible = false
	if level_idx < Levels.LEVELS.size() - 1:
		_load_level(level_idx + 1)
	else:
		_exit_to_world()


func _show_next_hint() -> void:
	var lv: Dictionary = Levels.LEVELS[level_idx]
	var hints: Array = lv.hints
	if hints.is_empty():
		return
	var h := str(hints[mini(hint_step, hints.size() - 1)])
	hint_step += 1
	hints_used += 1
	_hint_label.text = "💡 힌트 %d/%d: %s" % [mini(hint_step, hints.size()), hints.size(), h]
	_hint_banner.visible = true
	_telemetry("record_operation", ["hint", true, h, {}, {}, {"stage": Levels.STAGE_ID, "level": level_idx + 1, "hint_step": hint_step}])


func _set_log(msg: String, col: Color) -> void:
	last_log = msg
	last_log_color = col
	_log_action_label.text = msg
	_log_action_label.add_theme_color_override("font_color", col)


func _update_vars_ui() -> void:
	if current_vars.is_empty():
		_vars_label.text = "변수: -"
		return
	var parts: PackedStringArray = []
	for k in current_vars.keys():
		parts.append("%s = %s" % [str(k), str(current_vars[k])])
	_vars_label.text = "  |  ".join(parts)


func _update_line_highlights() -> void:
	for i in _line_rows.size():
		var line_no := i + 1
		var row_p := _line_rows[i]
		var arrow := _line_arrows[i]
		if line_no == error_line:
			row_p.add_theme_stylebox_override("panel", _flat_box(Color(0.65, 0.16, 0.20, 0.55), RED, 1, 4, 2))
			arrow.text = "!"
			arrow.add_theme_color_override("font_color", RED)
		elif line_no == active_line:
			row_p.add_theme_stylebox_override("panel", _flat_box(Color(0.18, 0.52, 0.26, 0.55), Color("4ade80"), 1, 4, 2))
			arrow.text = "▶"
			arrow.add_theme_color_override("font_color", GOLD)
		else:
			row_p.add_theme_stylebox_override("panel", _flat_box(Color(0, 0, 0, 0), Color(0, 0, 0, 0), 0, 4, 2))
			arrow.text = " "


func _show_float(t: String, col: Color) -> void:
	_floating_text = t
	_floating_color = col
	_floating_timer = 0.85


func _animate_robot_to(target: Vector2) -> void:
	if absf(target.x - _robot_visual_pos.x) > 4.0:
		_robot_flip = (target.x < _robot_visual_pos.x)
	if _robot_tween != null and _robot_tween.is_valid():
		_robot_tween.kill()
	var dur: float = 0.25 / SPEEDS[speed_idx]
	_robot_tween = create_tween().set_parallel(true)
	_robot_tween.tween_method(func(p: Vector2):
		_robot_visual_pos = p
		_stage_canvas.queue_redraw(), _robot_visual_pos, target, dur).set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
	_robot_tween.tween_method(func(k: float):
		_robot_hop = sin(k * PI) * 14.0
		_stage_canvas.queue_redraw(), 0.0, 1.0, dur)


# ============================================================================
# PANTHEON COURTYARD SPRITE RENDERING (ALL 8 MODES)
# ============================================================================

func _default_robot_pos() -> Vector2:
	match mode:
		"stack_reverse", "queue_fifo", "bubble_sort", "binary_search", "data_mean":
			return _slot_robot_pos(0)
		"sql_filter", "sql_sum", "data_clean":
			return _row_robot_pos(0)
	return Vector2(280, 400)


func _slot_robot_pos(idx: int) -> Vector2:
	var n := maxi(slots_state.size(), 1)
	match mode:
		"stack_reverse", "queue_fifo":
			var w := 116.0
			var x0 := 386.0 - (n * w) * 0.5
			return Vector2(x0 + (idx + 0.5) * w, 344.0)
		"binary_search":
			var w := 82.0
			var x0 := 386.0 - (n * w) * 0.5
			return Vector2(x0 + (idx + 0.5) * w, 396.0)
		"data_mean":
			var w := 108.0
			var x0 := 386.0 - (n * w) * 0.5
			return Vector2(x0 + (idx + 0.5) * w, 368.0)
	var bw := 108.0
	var bx0 := 386.0 - (n * bw) * 0.5
	return Vector2(bx0 + (idx + 0.5) * bw, 498.0)


func _stack_robot_pos() -> Vector2:
	if mode == "queue_fifo":
		return Vector2(286.0, 466.0)
	return Vector2(268.0, 476.0)


func _output_robot_pos(idx: int) -> Vector2:
	return Vector2(414.0 + idx * 62.0, 474.0)


func _row_robot_pos(r: int) -> Vector2:
	return Vector2(118.0, 248.0 + r * 40.0)


func _draw_tex(key: String, rect: Rect2, modulate := Color.WHITE) -> void:
	if _tex.has(key) and _tex[key] != null:
		_stage_canvas.draw_texture_rect(_tex[key], rect, false, modulate)


func _draw_crate(rect: Rect2, label_txt: String, variant := "crate_blue") -> void:
	# 바닥 그림자
	_stage_canvas.draw_circle(Vector2(rect.position.x + rect.size.x * 0.5, rect.position.y + rect.size.y * 0.88), rect.size.x * 0.36, Color(0, 0, 0, 0.22))
	_draw_tex(variant, rect)
	# 상자 중앙 베이지 명판 위치에 숫자 표기
	var ty := rect.position.y + rect.size.y * 0.67
	_stage_canvas.draw_string(_ui_font, Vector2(rect.position.x, ty), label_txt, HORIZONTAL_ALIGNMENT_CENTER, rect.size.x, int(clampf(rect.size.x * 0.25, 13.0, 21.0)), INK)


func _draw_index_sign(center_x: float, y: float, idx_txt: String) -> void:
	var sr := Rect2(center_x - 24, y, 48, 28)
	_draw_tex("chip_parchment", sr)
	_stage_canvas.draw_string(_ui_font, Vector2(sr.position.x, sr.position.y + 20), idx_txt, HORIZONTAL_ALIGNMENT_CENTER, sr.size.x, 15, INK)
	# 시안 발광 바
	_stage_canvas.draw_rect(Rect2(center_x - 12, y + 30, 24, 5), CYAN, true)


func _draw_stage() -> void:
	match mode:
		"stack_reverse": _draw_ds_stack_stage()
		"queue_fifo":    _draw_ds_queue_stage()
		"bubble_sort":   _draw_algo_sort_stage()
		"binary_search": _draw_algo_bsearch_stage()
		"sql_filter":    _draw_sql_table_stage()
		"sql_sum":       _draw_sql_sum_stage()
		"data_clean":    _draw_data_clean_stage()
		"data_mean":     _draw_data_mean_stage()

	_draw_robot()


# ── Lv 1: 배열 & 스택 역순 복구 (시안 대표 장면 1:1 재현!) ──
func _draw_ds_stack_stage() -> void:
	var n := slots_state.size()
	var w := 116.0
	var x0 := 386.0 - (n * w) * 0.5

	# 상단: 인덱스 표지판(0..3) + 석재 바닥 슬롯 + 파란 데이터 상자(10..40)
	for i in n:
		var cx := x0 + (i + 0.5) * w
		_draw_index_sign(cx, 206.0, str(i))
		var is_act := i in active_indices
		var slot_r := Rect2(cx - 48, 252, 96, 72)
		_draw_tex("slot_active" if is_act else "slot_normal", slot_r)
		var crate_r := Rect2(cx - 38, 234, 76, 76)
		_draw_crate(crate_r, str(slots_state[i]), "crate_gold" if is_act else "crate_blue")

	# 좌하단: 황동·석재 U자형 스택 타워 + 내부 적재 상자
	var tower_r := Rect2(92, 376, 150, 192)
	_stage_canvas.draw_circle(Vector2(167, 558), 64, Color(0, 0, 0, 0.24))
	_draw_tex("stack_tower", tower_r)
	for i in stack_state.size():
		var is_top := (i == stack_state.size() - 1)
		var cr := Rect2(133, 478 - i * 44, 68, 62)
		_draw_crate(cr, str(stack_state[i]), "crate_gold" if is_top else "crate_blue")

	# 우하단: 초록 헤더 4슬롯 복구 작업대 (output_bench)
	var bench_r := Rect2(356, 396, 326, 178)
	_stage_canvas.draw_circle(Vector2(519, 558), 110, Color(0, 0, 0, 0.22))
	_draw_tex("output_bench", bench_r)
	_stage_canvas.draw_string(_ui_font, Vector2(bench_r.position.x, bench_r.position.y + 34), "복구 작업대", HORIZONTAL_ALIGNMENT_CENTER, bench_r.size.x, 14, Color.WHITE)
	for i in mini(output_state.size(), 4):
		var ox := 386.0 + i * 68.0
		_draw_crate(Rect2(ox, 444, 60, 60), str(output_state[i]), "crate_gold")


# ── Lv 2: 큐(FIFO) 컨베이어 벨트 ──
func _draw_ds_queue_stage() -> void:
	var n := slots_state.size()
	var w := 116.0
	var x0 := 386.0 - (n * w) * 0.5
	for i in n:
		var cx := x0 + (i + 0.5) * w
		_draw_index_sign(cx, 204.0, str(i))
		var is_act := i in active_indices
		_draw_tex("slot_active" if is_act else "slot_normal", Rect2(cx - 48, 250, 96, 70))
		_draw_crate(Rect2(cx - 37, 232, 74, 74), str(slots_state[i]), "crate_gold" if is_act else "crate_blue")

	# 좌하단: FIFO 컨베이어 벨트
	var belt_r := Rect2(68, 398, 274, 150)
	_draw_tex("queue_belt", belt_r)
	_stage_canvas.draw_string(_ui_font, Vector2(74, 392), "◀ FRONT     FIFO 벨트     REAR ◀", HORIZONTAL_ALIGNMENT_LEFT, -1, 14, INK)
	for i in mini(stack_state.size(), 4):
		_draw_crate(Rect2(96 + i * 54, 430, 54, 54), str(stack_state[i]), "crate_gold" if i == 0 else "crate_blue")

	# 우하단: 창구 완료 작업대
	var bench_r := Rect2(368, 396, 320, 176)
	_draw_tex("output_bench", bench_r)
	_stage_canvas.draw_string(_ui_font, Vector2(bench_r.position.x, bench_r.position.y + 34), "창구 완료", HORIZONTAL_ALIGNMENT_CENTER, bench_r.size.x, 14, Color.WHITE)
	for i in mini(output_state.size(), 4):
		_draw_crate(Rect2(396 + i * 67, 444, 58, 58), str(output_state[i]), "crate_gold")


# ── Lv 3: 버블 정렬 작업대 (석재 받침대 + 높이별 적재 상자 탑) ──
func _draw_algo_sort_stage() -> void:
	var n := slots_state.size()
	var bw := 108.0
	var x0 := 386.0 - (n * bw) * 0.5
	var base_y := 428.0

	for i in n:
		var cx := x0 + (i + 0.5) * bw
		var is_act := i in active_indices
		_draw_tex("slot_active" if is_act else "slot_normal", Rect2(cx - 48, base_y, 96, 70))
		_draw_index_sign(cx, base_y + 68, "[%d]" % i)

		var v := int(slots_state[i])
		var stack_cnt := clampi(roundi(float(v) / 10.0), 1, 4)
		for s in stack_cnt - 1:
			_draw_tex("crate_gold" if is_act else "crate_blue", Rect2(cx - 34, base_y - 36 - s * 32, 68, 62))
		var top_y := base_y - 38 - (stack_cnt - 1) * 32
		_draw_crate(Rect2(cx - 38, top_y, 76, 74), str(v), "crate_gold" if is_act else "crate_blue")


# ── Lv 4: 정렬된 서고 이진 탐색 (7칸 슬롯 + 크리스탈 계기판) ──
func _draw_algo_bsearch_stage() -> void:
	var low_v := int(current_vars.get("low", 0))
	var high_v := int(current_vars.get("high", slots_state.size() - 1))
	var mid_v := int(current_vars.get("mid", -1))

	var n := slots_state.size()
	var w := 82.0
	var x0 := 386.0 - (n * w) * 0.5
	for i in n:
		var cx := x0 + (i + 0.5) * w
		var in_range := (i >= low_v and i <= high_v)
		var is_mid := (i == mid_v)
		var is_found := (i == found_index)
		var tint := Color.WHITE if (in_range or is_found) else Color(0.55, 0.58, 0.65, 0.72)

		_draw_index_sign(cx, 224.0, "[%d]" % i)
		_draw_tex("slot_active" if (is_mid or is_found) else "slot_normal", Rect2(cx - 39, 274, 78, 60), tint)
		if in_range or is_found:
			_draw_crate(Rect2(cx - 34, 258, 68, 68), str(slots_state[i]), "crate_gold" if (is_mid or is_found) else "crate_blue")
		else:
			_draw_tex("crate_blue", Rect2(cx - 32, 260, 64, 64), tint)
			_stage_canvas.draw_string(_ui_font, Vector2(cx - 32, 303), str(slots_state[i]), HORIZONTAL_ALIGNMENT_CENTER, 64, 16, Color("334155"))

		var tags: PackedStringArray = []
		if i == low_v: tags.append("L")
		if i == mid_v: tags.append("MID")
		if i == high_v: tags.append("H")
		if not tags.is_empty():
			var tr := Rect2(cx - 30, 336, 60, 24)
			_draw_tex("row_green" if is_found else "row_normal", tr)
			_stage_canvas.draw_string(_code_font, Vector2(tr.position.x, tr.position.y + 17), "·".join(tags), HORIZONTAL_ALIGNMENT_CENTER, tr.size.x, 12, GOLD if is_mid else Color.WHITE)

	# 하단 중앙: 크리스탈 탐색 계기판
	var g_rect := Rect2(262, 444, 248, 144)
	_draw_tex("crystal_gauge", g_rect)
	var status_txt := "목표: 34 탐색 중" if found_index < 0 else "발견 위치: [%d]번!" % found_index
	_stage_canvas.draw_string(_ui_font, Vector2(g_rect.position.x, g_rect.position.y + 102), status_txt, HORIZONTAL_ALIGNMENT_CENTER, g_rect.size.x, 17, GOLD if found_index >= 0 else CYAN)


# ── Lv 5: SQL WHERE 조건 조회 (입체 원목·황동 레코드 바 + 작업대 결과) ──
func _draw_sql_table_stage() -> void:
	var x0 := 152.0
	var rw := 520.0
	# 컬럼 헤더 명패
	var hdr := Rect2(x0, 198, rw, 30)
	_draw_tex("chip_parchment", hdr)
	_stage_canvas.draw_string(_code_font, Vector2(x0 + 34, 218), "행    name         dept         score       상태", HORIZONTAL_ALIGNMENT_LEFT, -1, 13, INK)

	for i in rows_state.size():
		var row: Dictionary = rows_state[i]
		var rr := Rect2(x0, 232 + i * 40, rw, 38)
		var st := str(row_status.get(i, ""))
		var key := "row_green" if st == "selected" else "row_normal"
		var mod := Color(1.16, 1.14, 1.0) if i == active_row else Color.WHITE
		_draw_tex(key, rr, mod)
		var ty := rr.position.y + 24
		_stage_canvas.draw_string(_code_font, Vector2(x0 + 36, ty), str(i), HORIZONTAL_ALIGNMENT_LEFT, -1, 14, GOLD if i == active_row else Color("cbd5e1"))
		_stage_canvas.draw_string(_ui_font, Vector2(x0 + 88, ty), str(row.name), HORIZONTAL_ALIGNMENT_LEFT, -1, 15, Color.WHITE)
		_stage_canvas.draw_string(_ui_font, Vector2(x0 + 210, ty), str(row.dept), HORIZONTAL_ALIGNMENT_LEFT, -1, 15, CYAN if str(row.dept) == "개발" else Color("e2e8f0"))
		var sc = row.score
		if sc == null:
			_draw_tex("cube_null", Rect2(x0 + 318, rr.position.y + 5, 26, 26))
			_stage_canvas.draw_string(_code_font, Vector2(x0 + 348, ty), "NULL", HORIZONTAL_ALIGNMENT_LEFT, -1, 14, CYAN)
		else:
			_stage_canvas.draw_string(_code_font, Vector2(x0 + 332, ty), str(sc), HORIZONTAL_ALIGNMENT_LEFT, -1, 15, Color("fff7cc"))
		if st == "selected":
			_stage_canvas.draw_string(_ui_font, Vector2(x0 + 414, ty), "SELECT ✓", HORIZONTAL_ALIGNMENT_LEFT, -1, 13, Color("bbf7d0"))

	# 하단: SELECT 추출 완료 작업대
	var bench_r := Rect2(226, 476, 360, 148)
	_draw_tex("output_bench", bench_r)
	_stage_canvas.draw_string(_ui_font, Vector2(bench_r.position.x, bench_r.position.y + 29), "SELECT 결과", HORIZONTAL_ALIGNMENT_CENTER, bench_r.size.x, 13, Color.WHITE)
	for k in mini(result_rows.size(), 4):
		var r: Dictionary = result_rows[k]
		_draw_crate(Rect2(258 + k * 76, 516, 66, 66), "%s:%s" % [str(r.name), str(r.score)], "crate_gold")


# ── Lv 6: SQL SUM 집계 (레코드 바 + 크리스탈 합계 계기판) ──
func _draw_sql_sum_stage() -> void:
	var x0 := 152.0
	var rw := 520.0
	var hdr := Rect2(x0, 198, rw, 30)
	_draw_tex("chip_parchment", hdr)
	_stage_canvas.draw_string(_code_font, Vector2(x0 + 34, 218), "행      dept          region          amount", HORIZONTAL_ALIGNMENT_LEFT, -1, 13, INK)

	for i in rows_state.size():
		var row: Dictionary = rows_state[i]
		var rr := Rect2(x0, 232 + i * 40, rw, 38)
		var is_seoul := str(row.region) == "서울"
		var am = row.amount
		var key := "row_green" if (is_seoul and am != null and i < active_row) else "row_normal"
		_draw_tex(key, rr, Color(1.16, 1.14, 1.0) if i == active_row else Color.WHITE)
		var ty := rr.position.y + 24
		_stage_canvas.draw_string(_code_font, Vector2(x0 + 36, ty), str(i), HORIZONTAL_ALIGNMENT_LEFT, -1, 14, GOLD if i == active_row else Color("cbd5e1"))
		_stage_canvas.draw_string(_code_font, Vector2(x0 + 110, ty), str(row.dept), HORIZONTAL_ALIGNMENT_LEFT, -1, 15, Color.WHITE)
		_stage_canvas.draw_string(_ui_font, Vector2(x0 + 226, ty), str(row.region), HORIZONTAL_ALIGNMENT_LEFT, -1, 15, CYAN if is_seoul else Color("cbd5e1"))
		if am == null:
			_draw_tex("cube_null", Rect2(x0 + 356, rr.position.y + 5, 26, 26))
			_stage_canvas.draw_string(_code_font, Vector2(x0 + 388, ty), "NULL", HORIZONTAL_ALIGNMENT_LEFT, -1, 14, CYAN)
		else:
			_stage_canvas.draw_string(_code_font, Vector2(x0 + 372, ty), str(am), HORIZONTAL_ALIGNMENT_LEFT, -1, 15, Color("fff7cc"))

	var cur_tot := int(current_vars.get("total", 0))
	var g1 := Rect2(174, 480, 220, 134)
	var g2 := Rect2(422, 480, 220, 134)
	_draw_tex("crystal_gauge", g1)
	_draw_tex("crystal_gauge", g2)
	_stage_canvas.draw_string(_ui_font, Vector2(g1.position.x, g1.position.y + 96), "누적 total = %d" % cur_tot, HORIZONTAL_ALIGNMENT_CENTER, g1.size.x, 16, CYAN)
	var rep_s := "SUM 대기 중" if reported_value == null else "보고 SUM = %s" % str(reported_value)
	_stage_canvas.draw_string(_ui_font, Vector2(g2.position.x, g2.position.y + 96), rep_s, HORIZONTAL_ALIGNMENT_CENTER, g2.size.x, 16, GOLD if reported_value != null else Color("cbd5e1"))


# ── Lv 7: 데이터 탐색 결측(NULL) & 이상치 정제 ──
func _draw_data_clean_stage() -> void:
	var x0 := 152.0
	var rw := 520.0
	var hdr := Rect2(x0, 198, rw, 30)
	_draw_tex("chip_parchment", hdr)
	_stage_canvas.draw_string(_code_font, Vector2(x0 + 34, 218), "행    id       group        value         정제 상태", HORIZONTAL_ALIGNMENT_LEFT, -1, 13, INK)

	for i in rows_state.size():
		var row: Dictionary = rows_state[i]
		var rr := Rect2(x0, 232 + i * 40, rw, 38)
		var st := str(row_status.get(i, ""))
		var key := "row_green" if st == "kept" else ("row_red" if st == "dropped" else "row_normal")
		_draw_tex(key, rr, Color(1.16, 1.14, 1.0) if i == active_row else Color.WHITE)
		var ty := rr.position.y + 24
		_stage_canvas.draw_string(_code_font, Vector2(x0 + 36, ty), str(i), HORIZONTAL_ALIGNMENT_LEFT, -1, 14, GOLD if i == active_row else Color("cbd5e1"))
		_stage_canvas.draw_string(_code_font, Vector2(x0 + 88, ty), str(row.id), HORIZONTAL_ALIGNMENT_LEFT, -1, 14, Color.WHITE)
		_stage_canvas.draw_string(_code_font, Vector2(x0 + 172, ty), str(row.group), HORIZONTAL_ALIGNMENT_LEFT, -1, 15, Color.WHITE)
		var v = row.value
		if v == null:
			_draw_tex("cube_null", Rect2(x0 + 266, rr.position.y + 5, 26, 26))
			_stage_canvas.draw_string(_code_font, Vector2(x0 + 296, ty), "NULL", HORIZONTAL_ALIGNMENT_LEFT, -1, 14, CYAN)
		elif int(v) >= 100:
			_draw_tex("crate_red", Rect2(x0 + 264, rr.position.y + 4, 28, 28))
			_stage_canvas.draw_string(_code_font, Vector2(x0 + 298, ty), str(v), HORIZONTAL_ALIGNMENT_LEFT, -1, 15, Color("fecaca"))
		else:
			_stage_canvas.draw_string(_code_font, Vector2(x0 + 284, ty), str(v), HORIZONTAL_ALIGNMENT_LEFT, -1, 15, Color("fff7cc"))

		if st == "kept":
			_stage_canvas.draw_string(_ui_font, Vector2(x0 + 414, ty), "KEEP ✓", HORIZONTAL_ALIGNMENT_LEFT, -1, 13, Color("bbf7d0"))
		elif st == "dropped":
			_stage_canvas.draw_string(_ui_font, Vector2(x0 + 414, ty), "DROP ✕", HORIZONTAL_ALIGNMENT_LEFT, -1, 13, Color("fecaca"))

	var bench_r := Rect2(226, 476, 360, 148)
	_draw_tex("output_bench", bench_r)
	_stage_canvas.draw_string(_ui_font, Vector2(bench_r.position.x, bench_r.position.y + 29), "정제 완료 데이터", HORIZONTAL_ALIGNMENT_CENTER, bench_r.size.x, 13, Color.WHITE)
	for k in mini(result_rows.size(), 4):
		var r: Dictionary = result_rows[k]
		_draw_crate(Rect2(258 + k * 76, 516, 66, 66), "%s:%s" % [str(r.group), str(r.value)], "crate_gold")


# ── Lv 8: 데이터 탐색 이상치 제외 대표 평균 (깨진 빨간 이상치 상자 + 크리스탈 계기판) ──
func _draw_data_mean_stage() -> void:
	var n := slots_state.size()
	var w := 108.0
	var x0 := 386.0 - (n * w) * 0.5
	for i in n:
		var cx := x0 + (i + 0.5) * w
		var v := int(slots_state[i])
		var is_act := i in active_indices
		var is_out := v >= 80
		_draw_index_sign(cx, 214.0, "[%d]" % i)
		_draw_tex("slot_active" if is_act else "slot_normal", Rect2(cx - 46, 262, 92, 68))
		var ctype := "crate_red" if is_out else ("crate_gold" if is_act else "crate_blue")
		_draw_crate(Rect2(cx - 38, 244, 76, 76), str(v), ctype)

	var tot := int(current_vars.get("total", 0))
	var cnt := int(current_vars.get("cnt", 0))
	var g1 := Rect2(142, 434, 232, 142)
	var g2 := Rect2(404, 434, 232, 142)
	_draw_tex("crystal_gauge", g1)
	_draw_tex("crystal_gauge", g2)
	_stage_canvas.draw_string(_ui_font, Vector2(g1.position.x, g1.position.y + 98), "합계 %d  /  개수 %d" % [tot, cnt], HORIZONTAL_ALIGNMENT_CENTER, g1.size.x, 16, CYAN)
	var rep_txt := "대표 평균 대기 중" if reported_value == null else "대표 평균 = %s" % str(reported_value)
	_stage_canvas.draw_string(_ui_font, Vector2(g2.position.x, g2.position.y + 98), rep_txt, HORIZONTAL_ALIGNMENT_CENTER, g2.size.x, 16, GOLD if reported_value != null else Color("cbd5e1"))


# ── 주인공 흰색 SD 로봇 + 손에 든 미니 상자 + 시안 발광 말풍선 ──
func _draw_robot() -> void:
	var rpos := _robot_visual_pos + Vector2(0, -_robot_hop)
	_stage_canvas.draw_circle(_robot_visual_pos + Vector2(0, 26), 22.0, Color(0, 0, 0, 0.28))
	if _robot_tex != null:
		var rsize := Vector2(68, 68)
		var draw_r := Rect2(rpos - rsize * 0.5, rsize)
		if _robot_flip:
			draw_r.size.x = -rsize.x
			draw_r.position.x += rsize.x
		_stage_canvas.draw_texture_rect(_robot_tex, draw_r, false)
	else:
		_stage_canvas.draw_circle(rpos, 22.0, CYAN)

	# 운반 중인 상자가 있으면 로봇 앞손에 미니 상자 연출 (시안의 로봇 상자 들기 연출!)
	if carried_label != "":
		var hand_off := Vector2(-26, -6) if _robot_flip else Vector2(18, -6)
		_draw_crate(Rect2(rpos + hand_off - Vector2(18, 18), Vector2(40, 40)), carried_label, "crate_gold")

	# 시안 발광 액션 말풍선 (PUSH 20 등)
	if _floating_text != "":
		var bw := maxf(92.0, float(_floating_text.length()) * 10.0 + 22.0)
		var fp := Vector2(clampf(rpos.x - bw * 0.5, 12.0, 736.0 - bw), rpos.y - 62.0 - (1.0 - _floating_timer) * 8.0)
		var frect := Rect2(fp, Vector2(bw, 28))
		_stage_canvas.draw_rect(frect.grow(2), Color(0.37, 0.84, 1.0, 0.35), true)
		_stage_canvas.draw_rect(frect, Color("0b7285"), true)
		_stage_canvas.draw_rect(frect, Color("99e9f2"), false, 2.0)
		_stage_canvas.draw_string(_ui_font, fp + Vector2(4, 20), _floating_text, HORIZONTAL_ALIGNMENT_CENTER, bw - 8.0, 14, Color.WHITE)


# ============================================================================
# INPUT & NAVIGATION
# ============================================================================

func _unhandled_input(ev: InputEvent) -> void:
	if not (ev is InputEventKey and ev.pressed and not ev.echo):
		return
	match ev.keycode:
		KEY_ESCAPE:
			# 씬 전환 뒤에는 get_viewport() 가 null 이 되므로 먼저 처리 표시를 한다.
			get_viewport().set_input_as_handled()
			_exit_to_world()
		KEY_F:
			if not (get_viewport().gui_get_focus_owner() is LineEdit):
				_show_next_hint()
				get_viewport().set_input_as_handled()
		KEY_ENTER, KEY_KP_ENTER:
			if _clear_overlay.visible:
				_on_clear_next()
				get_viewport().set_input_as_handled()


func _exit_to_menu() -> void:
	_stop_playback()
	Catalog.selected_category = "CHALLENGE"
	get_tree().change_scene_to_file("res://scenes/Main.tscn")


func _exit_to_world() -> void:
	_stop_playback()
	var world = load("res://scripts/nodeverse_world.gd")
	if world.return_from_2d(get_tree()):
		return
	Catalog.selected_category = "CHALLENGE"
	get_tree().change_scene_to_file("res://scenes/Main.tscn")


func _telemetry(method: String, args: Array) -> void:
	var nm = get_node_or_null("/root/NetworkManager")
	if nm and nm.has_method(method):
		if nm.has_method("resolve_minigame") and nm.call("resolve_minigame", Levels.STAGE_ID)[0].is_empty():
			return
		nm.callv(method, args)
