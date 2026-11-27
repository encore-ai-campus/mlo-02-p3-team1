extends WalkStage
## ST03 스택 - 최근 작업 복구실
## 복구 레벨: 입고 레일의 상자를 차례로 탑에 넣고(push) 꺼내(pop) 복구 작업대에 목표 순서대로 놓는다.
## 괄호 레벨: 괄호도 상자다. 입고 레일에서 괄호 상자를 하나씩 집어, 여는 괄호는 탑에 push, 닫는 괄호는 탑에 가져가 짝이 맞으면 pop 한다.
##   짝이 안 맞거나 다 읽은 뒤에는 복구 작업대 앞 판정 발판(올바름 / 불일치 / 괄호 남음)에서 결과를 선언한다.

const CAP := 3
const LEVELS := [
	{"type": "order", "in": ["A", "B"], "out": ["B", "A"], "peek": true, "goal": "A, B를 쌓고 Peek로 top을 확인한 뒤 복구"},
	{"type": "order", "in": ["A", "B", "C"], "out": ["C", "B", "A"], "goal": "복구 순서 C → B → A 맞추기"},
	{"type": "order", "in": ["A", "B", "C"], "out": ["B", "C", "A"], "goal": "복구 순서 B → C → A 맞추기"},
	{"type": "bracket", "s": "([]{})", "goal": "괄호 상자 짝 맞추기: 여는 괄호는 push, 닫는 괄호는 탑에서 짝이면 pop"},
	{"type": "bracket", "s": "{[(])}", "goal": "괄호 상자 짝 맞추기: 짝이 안 맞으면 든 채로 '불일치' 발판에서 선언"},
	{"type": "bracket", "s": "(()", "goal": "괄호 상자를 다 처리하고 결과 판정하기"},
]
const PAIR := {")": "(", "]": "[", "}": "{"}
const ORDER_KINDS := ["tower", "intake", "output"]
const JUDGE := ["올바름", "불일치", "괄호 남음"]   # 판정 발판 0, 1, 2

var L: Dictionary
var stack: Array = []
var inbox: Array = []
var out: Array = []
var target: Array = []
var hand = null
var step := 0
var peeked := false
var board: Node2D
var pads: Node2D          # 바닥 발판(작업대 앞 판정 자리) - 로봇보다 아래에 그린다
var lever_sign: Node2D

func _init() -> void:
	stage_id = "ST03"
	stage_title = "최근 작업 복구실"
	npc_name = "복구실 장인"
	npc_portrait = preload("res://textures/npc_portraits/NPC03_portrait.png")
	level_count = LEVELS.size()
	code_keywords += ["char"]
	intro = [
		"어이쿠, 왔구나! 난 복구실 장인이란다. 잘못된 작업은 가장 최근 것부터 되돌려야 해. 그래서 여기엔 아주 특별한 탑이 있지.",
		"저 왼쪽 탑을 보렴. 입구가 위쪽 하나뿐이라, 상자는 맨 위에만 쌓을 수 있고 맨 위에서만 꺼낼 수 있어. 이런 구조를 '스택'이라고 한단다.",
		"나중에 들어간 게 먼저 나온다고 해서 후입선출, LIFO라고 불러. 접시를 쌓는 거랑 똑같지. 맨 아래 접시는 위를 다 치워야 꺼낼 수 있어.",
		"넣는 걸 push, 꺼내는 걸 pop, 맨 위를 'top'이라고 해. 실행 취소나 뒤로 가기가 다 스택으로 만들어졌단다.",
		"조작법! 입고 레일에서 E로 상자를 집고, 탑 앞에서 E를 누르면 push, 빈손으로 E를 누르면 pop이야. 작업대에는 정해진 순서대로만 놓을 수 있어. 잘못 쌓아서 막히면 Z로 한 걸음씩 되돌릴 수 있단다.",
		"뒤의 괄호 검사도 똑같이 상자를 옮기는 일이야. 괄호 상자를 레일에서 하나씩 집어서, 여는 괄호는 탑에 push, 닫는 괄호는 탑에 가져가 맨 위와 짝이 맞으면 함께 pop! 판정은 복구 작업대 앞 발판에서 한단다. 막히면 노란 화살표를 따라가!",
	]
	level_talk = [
		"먼저 살펴보는 법을 배우자. A, B를 탑에 넣고, 책상에서 E를 눌러 Peek로 맨 위를 확인해 보렴. Peek는 보기만 하니까 탑은 그대로란다. 그다음 B, A 순서로 복구해.",
		"첫 일감이야. A, B, C가 차례로 들어오는데 복구는 C, B, A 순서로 해야 해. 전부 탑에 넣었다가 꺼내면 저절로 거꾸로 되지!",
		"이번엔 B, C, A 순서야. 셋을 다 넣어 버리면 맨 위가 C라서 B를 먼저 꺼낼 수 없게 돼! 꺼낼 차례가 된 상자는 바로 꺼내면서 push와 pop을 번갈아 해 보렴. 막히면 Z로 되돌리면 돼.",
		"이제 괄호 검사야! 레일에 ( [ ] { } ) 상자가 차례로 와. 여는 괄호 상자는 탑에 넣고, 닫는 괄호 상자는 탑에 가져가서 맨 위와 짝이 맞으면 함께 꺼내렴. 다 처리하고 탑이 비면 복구 작업대 앞 '올바름' 발판에서 E로 선언해.",
		"{[(])} 이건 수상한데? 닫는 괄호 상자를 들었는데 탑 맨 위와 짝이 안 맞으면, 그 상자를 든 채로 복구 작업대 앞 '불일치' 발판에서 선언하렴.",
		"마지막은 (() 란다. 레일의 상자를 다 처리했는데 탑에 괄호가 남아 있으면 닫히지 않은 거야. 그땐 복구 작업대 앞 '괄호 남음' 발판에서 선언해.",
	]

func build_stage() -> void:
	board = Node2D.new()
	overlay.add_child(board)
	pads = make_floor_layer()
	# POP 레버 안내판 글자는 배경 그림에 들어 있다.
	lever_sign = Node2D.new()
	overlay.add_child(lever_sign)

func setup_level(n: int) -> void:
	L = LEVELS[n]
	stack = []
	out = []
	hand = null
	step = 0
	peeked = false
	goal_text = L.goal
	if L.type == "order":
		inbox = L.in.duplicate()
		target = L.out
	else:
		# 괄호 상자: 글자 위치(번호)를 들고 다닌다. 글자는 L.s[번호]
		inbox = range(L.s.length())
		target = []
	var bracket: bool = L.type == "bracket"
	# 꺼내기는 상자든 괄호든 모두 탑 앞에서 한다. POP 레버는 쓰지 않는다.
	spot("lever").enabled = false
	spot("desk").enabled = L.get("peek", false)
	spot("output").enabled = not bracket
	spot("intake").enabled = true
	for j in JUDGE.size():
		spot("judge", j).enabled = bracket
	lever_sign.modulate = Color(1, 1, 1, 0.35)
	_draw_pads()

func get_state() -> Dictionary:
	return {"s": stack, "i": inbox, "o": out, "h": hand, "t": step, "p": peeked}

func set_state(s: Dictionary) -> void:
	stack = s.s
	inbox = s.i
	out = s.o
	hand = s.h
	step = s.t
	peeked = s.p

func rebuild() -> void:
	var want := {}
	if L.type == "order":
		for i in stack.size():
			want[stack[i]] = {"text": stack[i], "pos": mark("Stack%d" % i), "scale": 0.72}
		for i in out.size():
			want[out[i]] = {"text": out[i], "pos": mark("Out%d" % i), "scale": 0.8}
		for i in inbox.size():
			want[inbox[i]] = {"text": inbox[i], "pos": mark("Inbox") + Vector2(-i * 60, -i * 14), "scale": 0.8}
		if hand != null:
			want[hand] = {"text": hand, "pos": hold_pos(), "scale": 0.8}
	else:
		for i in stack.size():
			want["b%d" % stack[i]] = {"text": L.s[stack[i]], "pos": mark("Stack%d" % i), "scale": 0.72}
		for i in mini(inbox.size(), 4):   # 레일에는 앞의 4개만 보인다
			want["b%d" % inbox[i]] = {"text": L.s[inbox[i]], "pos": mark("Inbox") + Vector2(-i * 60, -i * 14), "scale": 0.8}
		if hand != null:
			want["b%d" % hand] = {"text": L.s[hand], "pos": hold_pos(), "scale": 0.8}
	sync_items(want, hand if L.type == "order" else ("b%d" % hand if hand != null else null))
	_draw_board()

## 복구 작업대 앞 바닥 발판. 상자 레벨은 "여기서 놓기" 발판 1개, 괄호 레벨은 판정 발판 3개.
func _draw_pads() -> void:
	clear_children(pads)
	var list := []
	if L.type == "bracket":
		for j in JUDGE.size():
			list.append([spot("judge", j).position, JUDGE[j], [Color("4caf50"), Color("e05252"), Color("e8a33d")][j]])
	else:
		list.append([spot("output").position, "여기서 놓기", Color("5fd6ff")])
	for e in list:
		floor_pad(pads, e[0], e[1], e[2])

func _draw_board() -> void:
	clear_children(board)
	if L.type != "bracket":
		return
	# 작업대 위 세 칸에 판정 이름을 크게 써서 발판과 짝지어 보이게 한다
	for j in JUDGE.size():
		text_at(JUDGE[j], mark("Out%d" % j) + Vector2(0, -6), 20, [Color("8ee59a"), Color("ff8f8f"), Color("ffc46b")][j], 5, board)
	var s: String = L.s
	var w := 58.0
	var c := mark("Board")
	panel_at(Rect2(c.x - s.length() * w / 2 - 14, c.y - 44, s.length() * w + 28, 88), Color("3b2a1c"), StageHUD.INK, 4, board)
	for i in s.length():
		var fill := Color("f6e7c8")
		if i < step:
			fill = Color("8fa08b")
		elif hand != null and i == hand:
			fill = StageHUD.GOLD
		var x := c.x - s.length() * w / 2 + i * w
		panel_at(Rect2(x + 3, c.y - 34, w - 6, 68), fill, StageHUD.INK, 3, board)
		text_at(s[i], Vector2(x + w / 2, c.y), 38, StageHUD.INK, 0, board)

## 스택에 든 값을 글자로 (괄호 레벨은 번호로 들고 있다)
func _sv(v) -> String:
	return L.s[v] if L.type == "bracket" else str(v)

func _chars() -> Array:
	var a := []
	for v in stack:
		a.append(_sv(v))
	return a

func info_rows() -> Array:
	var rows := [["스택", "[" + ", ".join(_chars()) + "]"], ["top", "-" if stack.is_empty() else _sv(stack.back())], ["크기", "%d / %d" % [stack.size(), CAP]]]
	rows.append(["들고 있는 상자", "-" if hand == null else _sv(hand)])
	if L.type == "bracket":
		rows.append(["처리한 괄호", "%d / %d" % [step, L.s.length()]])
	return rows

func state_text() -> String:
	var cells := []
	for v in _chars():
		cells.append("'%s'" % v)
	var t := "stack = [lb]%s[rb]" % ", ".join(cells)
	t += "\ntop = %s" % ("없음" if stack.is_empty() else "'%s'" % _sv(stack.back()))
	if L.type == "order" and hand != null:
		t += "\ntemp = '%s'  [color=#7fbf7f]// 로봇이 든 상자[/color]" % hand
	elif L.type == "bracket" and hand != null:
		t += "\nch = '%s'  [color=#7fbf7f]// 로봇이 든 괄호[/color]" % L.s[hand]
	return t

func prompt(t: Interactable) -> String:
	if L.type == "order":
		match t.kind:
			"tower": return "push (%s 넣기)" % hand if hand != null else ("pop (%s 꺼내기)" % stack.back() if not stack.is_empty() else "탑 (비어 있음)")
			"intake": return "다음 상자 집기" if hand == null else "입고 레일"
			"output": return "%d번 자리에 놓기" % (out.size() + 1) if hand != null else "복구 작업대"
			"desk": return "Peek (맨 위 보기)"
	else:
		match t.kind:
			"intake": return "다음 괄호 상자 집기" if hand == null and not inbox.is_empty() else "입고 레일"
			"tower":
				if hand == null:
					return "괄호 탑"
				var ch: String = L.s[hand]
				return "push '%s'" % ch if not PAIR.has(ch) else "'%s' 짝 맞춰 pop" % ch
			"judge": return "%s 선언" % JUDGE[t.index]
	return t.prompt

func interact(t: Interactable) -> void:
	if L.type == "order":
		_order(t)
	else:
		_bracket(t)
	rebuild()

func _order(t: Interactable) -> void:
	match t.kind:
		"intake":
			if hand != null:
				wrong("이미 상자를 들고 있어요.")
			elif inbox.is_empty():
				wrong("입고 레일이 비어 있어요.")
			else:
				snapshot()
				hand = inbox.pop_front()
				code("temp = '%s';" % hand, "새 상자")
		"tower":
			if hand != null:
				if stack.size() >= CAP:
					wrong("탑이 가득 찼어요. 먼저 pop 하세요.")
					return
				snapshot()
				stack.append(hand)
				code_replace("stack.push('%s');" % hand, "맨 위에 쌓기")
				hand = null
				moves += 1
				if not _solvable(inbox, stack, out.size()):
					var need: String = target[out.size()]
					hud.toast("이렇게 쌓으면 %s 를 먼저 꺼낼 수 없어요. Z로 방금 push를 되돌리세요." % need, StageHUD.RED, 5.0)
			elif stack.is_empty():
				wrong("탑이 비어 있어요.")
			elif L.get("peek", false) and not peeked:
				wrong("꺼내기 전에 책상에서 Peek로 맨 위를 먼저 확인해 보세요.")
			else:
				snapshot()
				hand = stack.pop_back()
				code("temp = stack.pop();", "'%s' 꺼내기" % hand)
		"desk":
			if stack.is_empty():
				wrong("탑이 비어 있어서 볼 수 있는 값이 없어요.")
			elif not inbox.is_empty() or hand != null:
				wrong("상자를 모두 탑에 넣은 다음 확인해 보세요.")
			else:
				snapshot()
				peeked = true
				code("x = stack.peek();", "'%s', 탑은 그대로" % stack.back())
				good("맨 위는 %s예요. Peek는 값을 꺼내지 않아요." % stack.back())
		"output":
			if hand == null:
				wrong("먼저 상자를 들고 오세요.")
			elif L.get("peek", false) and not peeked:
				wrong("먼저 탑에 넣고 Peek로 맨 위를 확인해 보세요.")
			elif hand != target[out.size()]:
				wrong("지금 복구할 상자는 %s 예요." % target[out.size()])
			else:
				snapshot()
				out.append(hand)
				code("result.add('%s');" % hand, "%d번째 복구" % out.size())
				hand = null
				moves += 1
				if out == target:
					win("복구 순서 %s 완성!\n실수 %d회" % [" → ".join(out), mistakes])

func _bracket(t: Interactable) -> void:
	var s: String = L.s
	match t.kind:
		"intake":
			if hand != null:
				wrong("이미 괄호 상자를 들고 있어요.")
			elif inbox.is_empty():
				wrong("레일이 비었어요. 작업대 앞 '올바름'이나 '괄호 남음' 발판에서 판정하세요.")
			else:
				snapshot()
				hand = inbox.pop_front()
				code("ch = '%s';" % s[hand], "%d번째 괄호" % (hand + 1))
		"tower":
			if hand == null:
				wrong("먼저 입고 레일에서 다음 괄호 상자를 집어 오세요.")
				return
			var ch: String = s[hand]
			if not PAIR.has(ch):
				if stack.size() >= CAP:
					wrong("탑이 가득 찼어요.")
					return
				snapshot()
				stack.append(hand)
				code("stack.push('%s');" % ch, "여는 괄호")
				hand = null
				step += 1
				moves += 1
			elif not stack.is_empty() and s[stack.back()] == PAIR[ch]:
				snapshot()
				var top: int = stack.pop_back()
				code("stack.pop();", "'%s' 와 '%s' 짝" % [s[top], ch])
				hand = null
				step += 1
				moves += 1
			else:
				wrong("'%s' 의 짝이 맨 위와 맞지 않아요. 이 상자를 든 채로 '불일치' 발판에서 선언!" % ch)
		"judge":
			if t.index == 1:
				var bad: bool = hand != null and PAIR.has(s[hand]) and (stack.is_empty() or s[stack.back()] != PAIR[s[hand]])
				if not bad:
					wrong("지금은 짝이 어긋난 괄호를 들고 있지 않아요.")
					return
				snapshot()
				moves += 1
				code("return false;", "'%s' 짝이 안 맞음" % s[hand])
				win("정답! '%s' 에서 짝이 어긋나는 걸 찾아냈어요.\n실수 %d회" % [s[hand], mistakes])
				return
			if hand != null or not inbox.is_empty():
				wrong("아직 괄호 상자를 다 처리하지 않았어요.")
				return
			var correct := 0 if stack.is_empty() else 2
			if t.index != correct:
				wrong("스택 상태를 다시 보세요.")
				return
			code("return %s;" % ("true" if correct == 0 else "false"), "스택이 비었나?")
			win("판정 정답! " + ("스택이 비어 올바른 괄호예요." if correct == 0 else "닫히지 않은 괄호 %d개가 남았어요." % stack.size()) + "\n실수 %d회" % mistakes)

## 상자 복구 레벨: 지금 상태에서 목표 순서를 끝까지 맞출 수 있는지 (막혔는지 알려 주기 위해)
func _solvable(ib: Array, st: Array, done: int) -> bool:
	if done >= target.size():
		return true
	var want_box: String = target[done]
	if not st.is_empty() and st.back() == want_box:
		return _solvable(ib, st.slice(0, st.size() - 1), done + 1)
	if ib.is_empty():
		return false
	if ib[0] == want_box and _solvable(ib.slice(1), st, done + 1):
		return true
	if st.size() < CAP:
		return _solvable(ib.slice(1), st + [ib[0]], done)
	return false

func summary_code() -> void:
	if L.type != "bracket":
		code("")
		code("// 나중에 넣은 것이 먼저 나와요 (LIFO)")

func next_action() -> Array:
	if L.type == "order":
		if L.get("peek", false) and not peeked:
			if hand != null:
				return [spot("tower"), "탑에 push"]
			if not inbox.is_empty():
				return [spot("intake"), "다음 상자 집기"]
			return [spot("desk"), "Peek로 맨 위 확인"]
		if hand != null:
			if hand == target[out.size()]:
				return [spot("output"), "복구 작업대에 놓기"]
			return [spot("tower"), "탑에 push"]
		if not stack.is_empty() and stack.back() == target[out.size()]:
			return [spot("tower"), "%s pop" % stack.back()]
		if not inbox.is_empty():
			return [spot("intake"), "다음 상자 집기"]
		return [null, ""]
	var s: String = L.s
	if hand == null:
		if not inbox.is_empty():
			return [spot("intake"), "다음 괄호 상자 집기"]
		return [spot("judge", 0), "올바름 선언"] if stack.is_empty() else [spot("judge", 2), "괄호 남음 선언"]
	var ch := s[hand]
	if not PAIR.has(ch):
		return [spot("tower"), "'%s' push" % ch]
	if not stack.is_empty() and s[stack.back()] == PAIR[ch]:
		return [spot("tower"), "'%s' 짝 맞춰 pop" % ch]
	return [spot("judge", 1), "불일치 선언"]
