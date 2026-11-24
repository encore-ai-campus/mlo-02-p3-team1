class_name PythonMiniVM
extends RefCounted
## 최종 도전용 경량 Python 서브셋 인터프리터 (샌드박스).
## 지원 문법: for .. in range(..), while, if / elif / else, 변수 대입(=, +=, -=),
## 산술(+,-,*,//,%), 비교(==,!=,<,<=,>,>=), 논리(and,or,not), 로봇 API 함수 호출.
## 모든 실행은 최대 스텝 수(max_steps)로 보호되어 무한 루프 시 안전하게 중단된다.

const MAX_STEPS_DEFAULT := 240

class Stmt:
	var kind: String = ""        # "call", "assign", "for", "while", "if", "pass"
	var line: int = 1
	var data: Dictionary = {}
	var body: Array = []         # Array[Stmt]
	var branches: Array = []     # for "if": Array[{"cond": String, "line": int, "body": Array[Stmt]}]

	func _init(k: String, l: int, d: Dictionary = {}) -> void:
		kind = k
		line = l
		data = d


## 소스 코드를 실행하고 트레이스 결과를 반환한다.
## sim_host 는 다음 메서드를 제공해야 한다:
##   - sim_call(func_name: String, args: Array) -> Dictionary {"ok": bool, "value": Variant, "action": Dictionary, "error": String}
## 반환:
##   {"ok": bool, "error": String, "error_line": int, "steps": Array[Dictionary], "final_vars": Dictionary}
static func execute(source: String, sim_host: Object, max_steps: int = MAX_STEPS_DEFAULT) -> Dictionary:
	var parsed := _parse(source)
	if not parsed.ok:
		return {
			"ok": false,
			"error": parsed.error,
			"error_line": parsed.error_line,
			"steps": [],
			"final_vars": {},
		}
	var ctx := {
		"vars": {},
		"steps": [],
		"step_count": 0,
		"max_steps": max_steps,
		"host": sim_host,
		"error": "",
		"error_line": 0,
		"loop_ctrl": "",
	}
	_exec_block(parsed.stmts, ctx)
	if ctx.error != "":
		return {
			"ok": false,
			"error": ctx.error,
			"error_line": ctx.error_line,
			"steps": ctx.steps,
			"final_vars": ctx.vars.duplicate(true),
		}
	return {
		"ok": true,
		"error": "",
		"error_line": 0,
		"steps": ctx.steps,
		"final_vars": ctx.vars.duplicate(true),
	}


# ============================================================================
# 1. PARSER (Indentation-based Python subset)
# ============================================================================

static func _parse(source: String) -> Dictionary:
	var raw_lines := source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
	var tokens: Array = [] # [{"indent": int, "text": String, "line": int}]
	for i in raw_lines.size():
		var raw: String = raw_lines[i]
		var stripped := _strip_comment(raw)
		if stripped.strip_edges() == "":
			continue
		var indent := _count_indent(raw)
		tokens.append({"indent": indent, "text": stripped.strip_edges(), "line": i + 1})

	var cursor := [0]
	var res := _parse_block(tokens, cursor, 0)
	if not res.ok:
		return res
	if cursor[0] < tokens.size():
		var tok: Dictionary = tokens[cursor[0]]
		return {"ok": false, "error": "들여쓰기가 맞지 않습니다.", "error_line": tok.line, "stmts": []}
	return {"ok": true, "error": "", "error_line": 0, "stmts": res.stmts}


static func _strip_comment(line: String) -> String:
	var in_s := false
	var in_d := false
	for i in line.length():
		var ch := line.substr(i, 1)
		if ch == "'" and not in_d:
			in_s = not in_s
		elif ch == "\"" and not in_s:
			in_d = not in_d
		elif ch == "#" and not in_s and not in_d:
			return line.substr(0, i)
	return line


static func _count_indent(line: String) -> int:
	var n := 0
	for i in line.length():
		var ch := line.substr(i, 1)
		if ch == " ":
			n += 1
		elif ch == "\t":
			n += 4
		else:
			break
	return n


static func _parse_block(tokens: Array, cursor: Array, expected_indent: int) -> Dictionary:
	var stmts: Array = []
	while cursor[0] < tokens.size():
		var tok: Dictionary = tokens[cursor[0]]
		if tok.indent < expected_indent:
			break
		if tok.indent > expected_indent:
			return {"ok": false, "error": "예상치 못한 들여쓰기입니다.", "error_line": tok.line, "stmts": []}
		var text: String = tok.text
		var line_no: int = tok.line

		if text.begins_with("elif ") or text == "else:" or text.begins_with("else "):
			return {"ok": false, "error": "짝이 맞는 if 문이 없습니다.", "error_line": line_no, "stmts": []}

		if text.begins_with("for "):
			if not text.ends_with(":"):
				return {"ok": false, "error": "for 문 끝에는 콜론(:)이 필요합니다.", "error_line": line_no, "stmts": []}
			var header := text.substr(4, text.length() - 5).strip_edges()
			var in_pos := header.find(" in ")
			if in_pos < 0:
				return {"ok": false, "error": "for 문 형식이 올바르지 않습니다. (예: for i in range(5):)", "error_line": line_no, "stmts": []}
			var var_name := header.substr(0, in_pos).strip_edges()
			var iter_expr := header.substr(in_pos + 4).strip_edges()
			if not _is_ident(var_name):
				return {"ok": false, "error": "반복 변수 이름이 올바르지 않습니다: %s" % var_name, "error_line": line_no, "stmts": []}
			cursor[0] += 1
			var body_res := _parse_indented_body(tokens, cursor, expected_indent, line_no)
			if not body_res.ok:
				return body_res
			var st := Stmt.new("for", line_no, {"var": var_name, "iter": iter_expr})
			st.body = body_res.stmts
			stmts.append(st)

		elif text.begins_with("while "):
			if not text.ends_with(":"):
				return {"ok": false, "error": "while 문 끝에는 콜론(:)이 필요합니다.", "error_line": line_no, "stmts": []}
			var cond := text.substr(6, text.length() - 7).strip_edges()
			cursor[0] += 1
			var body_res := _parse_indented_body(tokens, cursor, expected_indent, line_no)
			if not body_res.ok:
				return body_res
			var st := Stmt.new("while", line_no, {"cond": cond})
			st.body = body_res.stmts
			stmts.append(st)

		elif text.begins_with("if "):
			if not text.ends_with(":"):
				return {"ok": false, "error": "if 문 끝에는 콜론(:)이 필요합니다.", "error_line": line_no, "stmts": []}
			var cond := text.substr(3, text.length() - 4).strip_edges()
			cursor[0] += 1
			var body_res := _parse_indented_body(tokens, cursor, expected_indent, line_no)
			if not body_res.ok:
				return body_res
			var st := Stmt.new("if", line_no)
			st.branches.append({"cond": cond, "line": line_no, "body": body_res.stmts})
			# elif / else 체인 수집
			while cursor[0] < tokens.size() and tokens[cursor[0]].indent == expected_indent:
				var next_tok: Dictionary = tokens[cursor[0]]
				var nt: String = next_tok.text
				if nt.begins_with("elif "):
					if not nt.ends_with(":"):
						return {"ok": false, "error": "elif 문 끝에는 콜론(:)이 필요합니다.", "error_line": next_tok.line, "stmts": []}
					var econd := nt.substr(5, nt.length() - 6).strip_edges()
					cursor[0] += 1
					var ebody := _parse_indented_body(tokens, cursor, expected_indent, next_tok.line)
					if not ebody.ok:
						return ebody
					st.branches.append({"cond": econd, "line": next_tok.line, "body": ebody.stmts})
				elif nt == "else:":
					cursor[0] += 1
					var ebody := _parse_indented_body(tokens, cursor, expected_indent, next_tok.line)
					if not ebody.ok:
						return ebody
					st.branches.append({"cond": "__else__", "line": next_tok.line, "body": ebody.stmts})
					break
				else:
					break
			stmts.append(st)

		elif text == "pass":
			cursor[0] += 1
			stmts.append(Stmt.new("pass", line_no))

		elif text == "break":
			cursor[0] += 1
			stmts.append(Stmt.new("break", line_no))

		elif text == "continue":
			cursor[0] += 1
			stmts.append(Stmt.new("continue", line_no))

		else:
			# 대입문 (+=, -=, =) 또는 식/함수 호출
			var assign := _split_assignment(text)
			if assign.is_assign:
				if not _is_ident(assign.lhs):
					return {"ok": false, "error": "변수 이름이 올바르지 않습니다: %s" % assign.lhs, "error_line": line_no, "stmts": []}
				stmts.append(Stmt.new("assign", line_no, assign))
			else:
				stmts.append(Stmt.new("expr", line_no, {"expr": text}))
			cursor[0] += 1

	return {"ok": true, "error": "", "error_line": 0, "stmts": stmts}


static func _parse_indented_body(tokens: Array, cursor: Array, parent_indent: int, header_line: int) -> Dictionary:
	if cursor[0] >= tokens.size() or tokens[cursor[0]].indent <= parent_indent:
		return {"ok": false, "error": "블록 안에 실행할 코드가 필요합니다.", "error_line": header_line, "stmts": []}
	var body_indent: int = tokens[cursor[0]].indent
	return _parse_block(tokens, cursor, body_indent)


static func _split_assignment(text: String) -> Dictionary:
	var depth := 0
	var in_s := false
	var in_d := false
	for i in text.length():
		var ch := text.substr(i, 1)
		if ch == "'" and not in_d:
			in_s = not in_s
		elif ch == "\"" and not in_s:
			in_d = not in_d
		elif in_s or in_d:
			continue
		elif ch == "(" or ch == "[":
			depth += 1
		elif ch == ")" or ch == "]":
			depth -= 1
		elif depth == 0:
			var two := text.substr(i, 2)
			if two == "==" or two == "!=" or two == "<=" or two == ">=":
				continue
			if i > 0 and text.substr(i - 1, 1) in ["=", "!", "<", ">", "+", "-"]:
				continue
			if two == "+=" or two == "-=":
				return {
					"is_assign": true,
					"op": two,
					"lhs": text.substr(0, i).strip_edges(),
					"rhs": text.substr(i + 2).strip_edges(),
				}
			if ch == "=":
				return {
					"is_assign": true,
					"op": "=",
					"lhs": text.substr(0, i).strip_edges(),
					"rhs": text.substr(i + 1).strip_edges(),
				}
	return {"is_assign": false}


# ============================================================================
# 2. EXECUTOR
# ============================================================================

static func _tick(ctx: Dictionary, line_no: int) -> bool:
	ctx.step_count += 1
	if ctx.step_count > ctx.max_steps:
		ctx.error = "최대 실행 횟수(%d회)를 초과했습니다. 반복 조건을 확인하세요!" % ctx.max_steps
		ctx.error_line = line_no
		return false
	return true


static func _exec_block(stmts: Array, ctx: Dictionary) -> void:
	for st in stmts:
		if ctx.error != "" or ctx.loop_ctrl != "":
			return
		_exec_stmt(st, ctx)


static func _exec_stmt(st: Stmt, ctx: Dictionary) -> void:
	if not _tick(ctx, st.line):
		return
	match st.kind:
		"pass":
			ctx.steps.append({"line": st.line, "vars": ctx.vars.duplicate(true), "action": {"type": "noop"}})
		"break":
			ctx.loop_ctrl = "break"
			ctx.steps.append({"line": st.line, "vars": ctx.vars.duplicate(true), "action": {"type": "noop"}})
		"continue":
			ctx.loop_ctrl = "continue"
			ctx.steps.append({"line": st.line, "vars": ctx.vars.duplicate(true), "action": {"type": "noop"}})
		"expr":
			var r := _eval_expr(st.data.expr, ctx, st.line)
			if not r.ok:
				ctx.error = r.error
				ctx.error_line = st.line
		"assign":
			var r := _eval_expr(st.data.rhs, ctx, st.line)
			if not r.ok:
				ctx.error = r.error
				ctx.error_line = st.line
				return
			var lhs: String = st.data.lhs
			if st.data.op == "=":
				ctx.vars[lhs] = r.value
			elif st.data.op == "+=":
				if not ctx.vars.has(lhs):
					ctx.error = "정의되지 않은 변수입니다: %s" % lhs
					ctx.error_line = st.line
					return
				ctx.vars[lhs] = ctx.vars[lhs] + r.value
			elif st.data.op == "-=":
				if not ctx.vars.has(lhs):
					ctx.error = "정의되지 않은 변수입니다: %s" % lhs
					ctx.error_line = st.line
					return
				ctx.vars[lhs] = ctx.vars[lhs] - r.value
			ctx.steps.append({
				"line": st.line,
				"vars": ctx.vars.duplicate(true),
				"action": {"type": "var", "name": lhs, "value": ctx.vars[lhs]},
			})
		"for":
			var iter_r := _eval_range(st.data.iter, ctx, st.line)
			if not iter_r.ok:
				ctx.error = iter_r.error
				ctx.error_line = st.line
				return
			var var_name: String = st.data.var
			for v in iter_r.values:
				if ctx.error != "":
					return
				ctx.vars[var_name] = v
				ctx.steps.append({
					"line": st.line,
					"vars": ctx.vars.duplicate(true),
					"action": {"type": "loop", "var": var_name, "value": v},
				})
				_exec_block(st.body, ctx)
				if ctx.loop_ctrl == "break":
					ctx.loop_ctrl = ""
					break
				elif ctx.loop_ctrl == "continue":
					ctx.loop_ctrl = ""
		"while":
			while true:
				if not _tick(ctx, st.line):
					return
				var cond_r := _eval_expr(st.data.cond, ctx, st.line)
				if not cond_r.ok:
					ctx.error = cond_r.error
					ctx.error_line = st.line
					return
				if not _truthy(cond_r.value):
					break
				ctx.steps.append({
					"line": st.line,
					"vars": ctx.vars.duplicate(true),
					"action": {"type": "branch", "cond": true},
				})
				_exec_block(st.body, ctx)
				if ctx.error != "":
					return
				if ctx.loop_ctrl == "break":
					ctx.loop_ctrl = ""
					break
				elif ctx.loop_ctrl == "continue":
					ctx.loop_ctrl = ""
		"if":
			for br in st.branches:
				if br.cond == "__else__":
					ctx.steps.append({
						"line": br.line,
						"vars": ctx.vars.duplicate(true),
						"action": {"type": "branch", "cond": true},
					})
					_exec_block(br.body, ctx)
					return
				var cr := _eval_expr(br.cond, ctx, br.line)
				if not cr.ok:
					ctx.error = cr.error
					ctx.error_line = br.line
					return
				if _truthy(cr.value):
					ctx.steps.append({
						"line": br.line,
						"vars": ctx.vars.duplicate(true),
						"action": {"type": "branch", "cond": true},
					})
					_exec_block(br.body, ctx)
					return


static func _eval_range(iter_expr: String, ctx: Dictionary, line_no: int) -> Dictionary:
	var t := iter_expr.strip_edges()
	if not (t.begins_with("range(") and t.ends_with(")")):
		return {"ok": false, "error": "for 문은 range(...) 형태만 지원합니다.", "values": []}
	var inner := t.substr(6, t.length() - 7).strip_edges()
	var parts := _split_top_level(inner, ",")
	if parts.size() < 1 or parts.size() > 3:
		return {"ok": false, "error": "range() 인자 개수가 올바르지 않습니다.", "values": []}
	var nums: Array[int] = []
	for p in parts:
		var er := _eval_expr(p, ctx, line_no)
		if not er.ok:
			return {"ok": false, "error": er.error, "values": []}
		if not (er.value is int or er.value is float):
			return {"ok": false, "error": "range() 안에는 숫자가 필요합니다.", "values": []}
		nums.append(int(er.value))
	var start_v := 0
	var stop_v := 0
	var step_v := 1
	if nums.size() == 1:
		stop_v = nums[0]
	elif nums.size() == 2:
		start_v = nums[0]
		stop_v = nums[1]
	else:
		start_v = nums[0]
		stop_v = nums[1]
		step_v = nums[2]
	if step_v == 0:
		return {"ok": false, "error": "range()의 간격은 0이 될 수 없습니다.", "values": []}
	var vals: Array = []
	var cur := start_v
	var guard := 0
	while (step_v > 0 and cur < stop_v) or (step_v < 0 and cur > stop_v):
		vals.append(cur)
		cur += step_v
		guard += 1
		if guard > 100:
			return {"ok": false, "error": "range() 범위가 너무 큽니다 (최대 100).", "values": []}
	return {"ok": true, "error": "", "values": vals}


# ============================================================================
# 3. EXPRESSION EVALUATOR
# ============================================================================

static func _eval_expr(expr: String, ctx: Dictionary, line_no: int) -> Dictionary:
	var s := expr.strip_edges()
	if s == "":
		return {"ok": false, "error": "빈칸이 비어 있습니다! 코드를 채워 주세요.", "value": null}
	if s.begins_with("___"):
		return {"ok": false, "error": "아직 채우지 않은 빈칸(%s)이 있습니다." % s, "value": null}

	# 외곽 괄호 제거
	while _wrapped_in_parens(s):
		s = s.substr(1, s.length() - 2).strip_edges()

	# 1. 논리 연산자: or (가장 낮은 우선순위)
	var or_parts := _split_keyword_op(s, "or")
	if or_parts.size() > 1:
		for p in or_parts:
			var r := _eval_expr(p, ctx, line_no)
			if not r.ok:
				return r
			if _truthy(r.value):
				return {"ok": true, "value": true}
		return {"ok": true, "value": false}

	# 2. 논리 연산자: and
	var and_parts := _split_keyword_op(s, "and")
	if and_parts.size() > 1:
		for p in and_parts:
			var r := _eval_expr(p, ctx, line_no)
			if not r.ok:
				return r
			if not _truthy(r.value):
				return {"ok": true, "value": false}
		return {"ok": true, "value": true}

	# 3. 단항 not
	if s.begins_with("not "):
		var r := _eval_expr(s.substr(4), ctx, line_no)
		if not r.ok:
			return r
		return {"ok": true, "value": not _truthy(r.value)}

	# 4. 비교 연산자
	var cmp := _split_comparison(s)
	if cmp.found:
		var lr := _eval_expr(cmp.left, ctx, line_no)
		if not lr.ok:
			return lr
		var rr := _eval_expr(cmp.right, ctx, line_no)
		if not rr.ok:
			return rr
		return {"ok": true, "value": _apply_cmp(cmp.op, lr.value, rr.value)}

	# 5. 덧셈 / 뺄셈
	var add := _split_binary_rtl(s, ["+", "-"])
	if add.found:
		var lr := _eval_expr(add.left, ctx, line_no)
		if not lr.ok:
			return lr
		var rr := _eval_expr(add.right, ctx, line_no)
		if not rr.ok:
			return rr
		if add.op == "+":
			if lr.value is String or rr.value is String:
				return {"ok": true, "value": str(lr.value) + str(rr.value)}
			return {"ok": true, "value": lr.value + rr.value}
		return {"ok": true, "value": lr.value - rr.value}

	# 6. 곱셈 / 정수 나눗셈 / 나머지
	var mul := _split_binary_rtl(s, ["//", "*", "%"])
	if mul.found:
		var lr := _eval_expr(mul.left, ctx, line_no)
		if not lr.ok:
			return lr
		var rr := _eval_expr(mul.right, ctx, line_no)
		if not rr.ok:
			return rr
		if mul.op == "*":
			return {"ok": true, "value": lr.value * rr.value}
		if int(rr.value) == 0:
			return {"ok": false, "error": "0으로 나눌 수 없습니다.", "value": null}
		if mul.op == "//":
			return {"ok": true, "value": int(lr.value) / int(rr.value)}
		return {"ok": true, "value": int(lr.value) % int(rr.value)}

	# 7. 단항 마이너스
	if s.begins_with("-") and s.length() > 1:
		var ur := _eval_expr(s.substr(1), ctx, line_no)
		if not ur.ok:
			return ur
		return {"ok": true, "value": -ur.value}

	# 8. 리터럴: 문자열
	if (s.begins_with("\"") and s.ends_with("\"")) or (s.begins_with("'") and s.ends_with("'")):
		if s.length() >= 2:
			return {"ok": true, "value": s.substr(1, s.length() - 2)}

	# 9. 리터럴: None / 불린 / 정수
	if s == "None" or s == "null":
		return {"ok": true, "value": null}
	if s == "True" or s == "true":
		return {"ok": true, "value": true}
	if s == "False" or s == "false":
		return {"ok": true, "value": false}
	if s.is_valid_int():
		return {"ok": true, "value": s.to_int()}

	# 10. 함수 호출: name(arg1, arg2, ...)
	var paren_idx := s.find("(")
	if paren_idx > 0 and s.ends_with(")"):
		var fname := s.substr(0, paren_idx).strip_edges()
		if _is_ident(fname):
			var arg_str := s.substr(paren_idx + 1, s.length() - paren_idx - 2).strip_edges()
			var args: Array = []
			if arg_str != "":
				for ap in _split_top_level(arg_str, ","):
					var ar := _eval_expr(ap, ctx, line_no)
					if not ar.ok:
						return ar
					args.append(ar.value)
			var host = ctx.host
			if host == null or not host.has_method("sim_call"):
				return {"ok": false, "error": "호출할 수 없는 함수입니다: %s()" % fname, "value": null}
			var call_res: Dictionary = host.call("sim_call", fname, args)
			if not call_res.get("ok", false):
				return {"ok": false, "error": str(call_res.get("error", "함수 실행 오류")), "value": null}
			if call_res.has("action") and call_res.action != null:
				ctx.steps.append({
					"line": line_no,
					"vars": ctx.vars.duplicate(true),
					"action": call_res.action,
				})
			return {"ok": true, "value": call_res.get("value", null)}

	# 11. 변수 조회
	if _is_ident(s):
		if ctx.vars.has(s):
			return {"ok": true, "value": ctx.vars[s]}
		return {"ok": false, "error": "알 수 없는 이름(변수 또는 함수)입니다: '%s'" % s, "value": null}

	return {"ok": false, "error": "해석할 수 없는 코드입니다: %s" % s, "value": null}


static func _truthy(v) -> bool:
	if v == null:
		return false
	if v is bool:
		return v
	if v is int or v is float:
		return v != 0
	if v is String:
		return v != ""
	return true


static func _apply_cmp(op: String, a, b) -> bool:
	if op == "==":
		return a == b
	if op == "!=":
		return a != b
	if a == null or b == null:
		return false
	match op:
		"<": return a < b
		"<=": return a <= b
		">": return a > b
		">=": return a >= b
	return false


static func _is_ident(s: String) -> bool:
	if s.is_empty():
		return false
	for i in s.length():
		var c := s.unicode_at(i)
		var ok := (c >= 65 and c <= 90) or (c >= 97 and c <= 122) or c == 95 or (i > 0 and c >= 48 and c <= 57)
		if not ok:
			return false
	return true


static func _wrapped_in_parens(s: String) -> bool:
	if not (s.begins_with("(") and s.ends_with(")")):
		return false
	var depth := 0
	var in_s := false
	var in_d := false
	for i in s.length():
		var ch := s.substr(i, 1)
		if ch == "'" and not in_d:
			in_s = not in_s
		elif ch == "\"" and not in_s:
			in_d = not in_d
		elif in_s or in_d:
			continue
		elif ch == "(":
			depth += 1
		elif ch == ")":
			depth -= 1
			if depth == 0 and i < s.length() - 1:
				return false
	return depth == 0


static func _split_top_level(s: String, sep: String) -> Array[String]:
	var out: Array[String] = []
	var depth := 0
	var in_s := false
	var in_d := false
	var start := 0
	for i in s.length():
		var ch := s.substr(i, 1)
		if ch == "'" and not in_d:
			in_s = not in_s
		elif ch == "\"" and not in_s:
			in_d = not in_d
		elif in_s or in_d:
			continue
		elif ch == "(" or ch == "[":
			depth += 1
		elif ch == ")" or ch == "]":
			depth -= 1
		elif depth == 0 and ch == sep:
			out.append(s.substr(start, i - start).strip_edges())
			start = i + 1
	out.append(s.substr(start).strip_edges())
	return out


static func _split_keyword_op(s: String, kw: String) -> Array[String]:
	var out: Array[String] = []
	var depth := 0
	var in_s := false
	var in_d := false
	var start := 0
	var pat := " %s " % kw
	var i := 0
	while i < s.length():
		var ch := s.substr(i, 1)
		if ch == "'" and not in_d:
			in_s = not in_s
		elif ch == "\"" and not in_s:
			in_d = not in_d
		elif not in_s and not in_d:
			if ch == "(":
				depth += 1
			elif ch == ")":
				depth -= 1
			elif depth == 0 and s.substr(i, pat.length()) == pat:
				out.append(s.substr(start, i - start).strip_edges())
				i += pat.length()
				start = i
				continue
		i += 1
	out.append(s.substr(start).strip_edges())
	return out


static func _split_comparison(s: String) -> Dictionary:
	var ops := ["==", "!=", "<=", ">=", "<", ">"]
	var depth := 0
	var in_s := false
	var in_d := false
	for i in s.length():
		var ch := s.substr(i, 1)
		if ch == "'" and not in_d:
			in_s = not in_s
		elif ch == "\"" and not in_s:
			in_d = not in_d
		elif in_s or in_d:
			continue
		elif ch == "(":
			depth += 1
		elif ch == ")":
			depth -= 1
		elif depth == 0:
			for op in ops:
				if s.substr(i, op.length()) == op:
					return {
						"found": true,
						"op": op,
						"left": s.substr(0, i).strip_edges(),
						"right": s.substr(i + op.length()).strip_edges(),
					}
	return {"found": false}


static func _split_binary_rtl(s: String, ops: Array) -> Dictionary:
	var depth := 0
	var in_s := false
	var in_d := false
	var best_idx := -1
	var best_op := ""
	var i := 0
	while i < s.length():
		var ch := s.substr(i, 1)
		if ch == "'" and not in_d:
			in_s = not in_s
		elif ch == "\"" and not in_s:
			in_d = not in_d
		elif not in_s and not in_d:
			if ch == "(":
				depth += 1
			elif ch == ")":
				depth -= 1
			elif depth == 0 and i > 0:
				for op in ops:
					if s.substr(i, op.length()) == op:
						# 단항 마이너스 방지
						var prev := s.substr(0, i).strip_edges()
						if op == "-" and (prev.is_empty() or prev.ends_with("(") or prev.ends_with(",") or prev.ends_with("+") or prev.ends_with("-") or prev.ends_with("*") or prev.ends_with("=")):
							continue
						best_idx = i
						best_op = op
						i += op.length() - 1
						break
		i += 1
	if best_idx > 0:
		return {
			"found": true,
			"op": best_op,
			"left": s.substr(0, best_idx).strip_edges(),
			"right": s.substr(best_idx + best_op.length()).strip_edges(),
		}
	return {"found": false}
