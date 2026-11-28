extends "res://scripts/minigames/learning_lab.gd"
## 데이터 탐색 실습: 데이터 점검(DATA02) · 데이터 정제(DATA01) · 통계 비교(DATA03) · 시각화 해석(DATA04).
## 원본 표는 절대 바꾸지 않고, 정답은 원본에서 다시 계산한다.

# ---------- 점검 데이터 ----------
const PROFILE_COLS := ["id", "age", "zip", "joined", "visits"]
const PROFILE_ROWS := [[1, 20, "06236", "2026-01-03", 0], [2, null, "01012", "2026-01-04", 12], [3, 30, "48058", "2026/02/11", 8], [4, 40, "61452", "2026-02-20", 5], [5, null, "34126", "2026-03-02", 3]]
const DICTIONARY := "데이터 사전: 1행 = 학생 1명 · age 나이(세) · zip 우편번호 · joined 가입일 · visits 방문 수(회) · 비어 있음(NULL)만 결측"
const TYPE_OPTS := ["숫자", "문자", "날짜"]
const UNIT_OPTS := ["세", "회", "원"]
const ROW_UNIT_OPTS := ["학생 1명", "방문 1회", "학교 1곳"]
## 점검 꼬리표 붙이기: 선반에서 꼬리표를 집어(E) 표 아래 열 자리로 들고 가 붙인다(E).
## 레벨마다 점검 관점이 하나씩: 자료형(dtype) → 결측(isna) → 형식(to_datetime)
const PROFILE_TARGETS := ["age", "zip", "joined", "visits"]
const PROFILE_LEVELS := [
	[{"lens": "자료형", "tags": ["숫자", "문자", "날짜"],
	  "answer": {"age": "숫자", "zip": "문자", "joined": "날짜", "visits": "숫자"},
	  "why": {"age": "나이는 평균을 낼 수 있는 숫자예요.", "zip": "우편번호는 더하거나 평균 내지 않아요. 01012의 앞자리 0을 지키려면 문자예요.",
		"joined": "가입일은 날짜예요. 날짜여야 기간을 계산하고 순서대로 정렬할 수 있어요.", "visits": "방문 횟수는 더하고 평균 낼 수 있는 숫자예요."},
	  "code": {"age": "df['age'].dtype", "zip": "df['zip'].dtype", "joined": "df['joined'].dtype", "visits": "df['visits'].dtype"}}],
	[{"lens": "결측", "tags": ["결측 있음", "결측 없음"],
	  "answer": {"age": "결측 있음", "zip": "결측 없음", "joined": "결측 없음", "visits": "결측 없음"},
	  "why": {"age": "age에는 비어 있는 칸(NULL)이 2개 있어요.", "zip": "zip은 다섯 칸 모두 값이 있어요.",
		"joined": "joined는 다섯 칸 모두 값이 있어요. 형식이 달라도 비어 있진 않아요.", "visits": "visits의 0은 '한 번도 안 왔다'는 값이에요. 비어 있는 것과 달라요."},
	  "code": {"age": "df['age'].isna().sum()", "zip": "df['zip'].isna().sum()", "joined": "df['joined'].isna().sum()", "visits": "df['visits'].isna().sum()"}}],
	[{"lens": "형식", "tags": ["형식 OK", "형식 섞임"],
	  "answer": {"age": "형식 OK", "zip": "형식 OK", "joined": "형식 섞임", "visits": "형식 OK"},
	  "why": {"age": "NULL은 결측이지 형식 문제가 아니에요. 값이 있는 칸은 모두 숫자예요.", "zip": "zip은 모두 숫자 다섯 자리로 같은 형식이에요.",
		"joined": "joined에 2026/02/11처럼 / 를 쓴 값이 섞여 있어요. 이대로면 날짜로 바꿀 때 실패해요.", "visits": "visits는 모두 정수예요."},
	  "code": {"age": "df['age'].dropna().astype(int)", "zip": "df['zip'].str.fullmatch(r'\\d{5}').all()", "joined": "pd.to_datetime(df['joined'], format='%Y-%m-%d')", "visits": "df['visits'].astype(int)"}}],
]

# ---------- 정제 데이터 (DA-02 기록 수리 공방) ----------
## 기록 카드를 하나씩 들고 버림함 · 중복함 · 수리대 · 투입구로 옮긴다.
const CLEAN_COLS := ["id", "group", "value", "date"]
const CLEAN_LEVELS := [
	[{"goal": "value가 빈 카드만 버림함에 넣고, 나머지는 투입구로", "dedup": "", "rows": [[1, "A", "10", "2026-01-01"], [2, "B", null, "2026-01-02"], [3, "A", "30", "2026-01-03"], [4, "C", null, "2026-01-04"], [5, "B", "0", "2026-01-05"]]}],
	[{"goal": "group+value가 같은 카드는 중복함, 빈 값은 버림함", "dedup": "group+value", "rows": [[1, "A", "10", "2026-01-01"], [2, "A", "10", "2026-01-02"], [3, "B", "20", "2026-01-02"], [4, "B", "25", "2026-01-03"], [5, "A", "10", "2026-01-05"], [6, "C", null, "2026-01-06"]]}],
	[{"goal": "모양이 틀린 카드는 수리대에서 고친 뒤 정리하기", "dedup": "all", "rows": [[1, " A ", "1,000", "2026/01/05"], [2, "A", "1000", "2026-01-05"], [3, "B", "abc", "2026-02-01"], [4, "B", "200", "2026-13-40"], [5, "C", "300", "2026-03-01"], [6, " C", "300", "2026-03-01"], [7, "D", "50", "2026-03-02"]]}],
]
const CLEAN_BINS := {"drop": "버림함", "dup": "중복함", "fix": "수리대", "keep": "투입구"}
const DEDUP_NAMES := {"group+value": "group+value", "all": "id 빼고 전부"}

# ---------- 통계 (DA-03 대표값 실험실) ----------
## 숫자 블록을 정렬 레일에 작은 수부터 꽂고, 답 블록을 평균·중앙값·범위 받침대에 올린다.
const STAT_FIELDS := ["mean", "median", "range"]
const STAT_LABELS := {"mean": "평균", "median": "중앙값", "range": "범위"}
const STAT_LEVELS := [
	[{"title": "점수 집단", "values": [4, 8, 6, 2], "fields": ["mean", "median", "range"], "choices": [5, 6, 4, 20, 8, 2, 7, 3]}],
	[{"title": "홀수 개", "values": [3, 9, 5], "fields": ["median"], "choices": [9, 3, 5, 17, 6, 4, 8, 1]},
	 {"title": "짝수 개", "values": [14, 10, 100, 12], "fields": ["median"], "choices": [12, 14, 34, 13, 10, 100, 11, 90]},
	 {"title": "NULL 포함", "values": [3, null, 9], "fields": ["mean"], "choices": [4, 12, 3, 6, 9, 2, 0, 8]}],
	[{"title": "이상치 비교", "values": [12, 100, 10, 14], "fields": ["mean", "median"], "choices": [13, 12, 90, 34, 100, 14, 10, 24],
	  "claims": ["100 하나 때문에 평균은 크게 달라지지만 중앙값은 적게 달라진다", "100을 지워야 올바른 데이터가 된다", "평균이 높으니 이 집단은 실력이 좋다"], "answer": 0},
	 {"title": "같은 평균 다른 분포", "values": [0, 20], "ref": [10, 10], "fields": ["range"], "choices": [0, 10, 20, 40, 2, 5, 15, 30],
	  "claims": ["두 집단의 평균은 10으로 같지만, 이 집단이 더 넓게 퍼져 있다", "평균이 같으니 두 집단은 같은 분포다", "이 집단이 공부를 덜 해서 범위가 크다"], "answer": 0},
	 {"title": "빈 집단", "values": [], "fields": [], "choices": [],
	  "claims": ["값이 하나도 없으니 평균을 계산할 수 없다", "빈 집단의 평균은 0이다", "빈 집단의 중앙값은 1이다"], "answer": 0}],
]

# ---------- 차트 (DA-04 차트 관측소) ----------
## 데이터 카드를 질문에 맞는 이젤에 꽂으면 차트가 자란다. 빈 값 카드는 빈 값 상자로.
const CHART_TYPES := ["막대", "선", "산점도"]
const CHART_LEVELS := [
	[{"question": "제품별 총판매량 중 가장 많이 팔린 제품은?", "cols": ["제품", "판매량"], "units": ["", "개"],
	  "rows": [["연필", 30], ["공책", 50], ["연필", 20], ["지우개", 10], ["공책", 5]], "type": "막대",
	  "claims": ["공책의 총판매량이 55개로 가장 많다", "연필이 가장 많이 팔렸다", "공책이 싸서 많이 팔렸다"], "answer": 0}],
	[{"question": "월별 판매량 변화에서 가장 높은 달은?", "cols": ["월", "판매량"], "units": ["", "개"],
	  "rows": [["2026-03", 12], ["2026-01", 10], ["2026-02", 15]], "type": "선",
	  "claims": ["2월 판매량이 15개로 가장 높다", "3월이 첫 달이라 가장 중요하다", "2월에 광고를 해서 늘었다"], "answer": 0}],
	[{"question": "키와 몸무게의 관계를 살펴보자", "cols": ["키", "몸무게"], "units": ["cm", "kg"],
	  "rows": [[150, 45], [160, 52], [170, 61], [null, 70], [180, 72], [175, null]], "type": "산점도",
	  "claims": ["키가 클수록 몸무게도 큰 경향이 보이지만 원인이라 단정할 수 없다", "키가 몸무게를 늘리는 원인이다", "두 값은 아무 관련이 없다"], "answer": 0}],
]

func lab_table() -> Dictionary:
	return {
		"profile": {"id": "DATA02", "title": "관측 준비실", "levels": 3, "art": "DATA02", "npc": "NPC00", "npc_name": "데이터 관측 담당자",
			"intro": ["큰일이에요! 이 학생 기록표를 내일 분석팀에 넘겨야 하는데, 점검 꼬리표가 하나도 안 붙어 있어요.",
				"꼬리표가 없으면 분석팀이 사고를 쳐요. 우편번호를 더해 버리거나, 빈 칸을 0으로 착각하거나, 날짜를 못 읽어서 멈춰 버리죠.",
				"오른쪽 선반에서 꼬리표를 E로 집고, 표 아래 열 자리(age · zip · joined · visits)로 들고 가서 E로 붙여 주세요. 네 열에 다 붙이면 끝이에요!"],
			"talk": ["1단계는 자료형 꼬리표예요. 이 열을 계산하는지(숫자), 이름처럼 쓰는지(문자), 날짜인지 표를 보고 붙여 주세요.",
				"2단계는 결측 꼬리표예요. 비어 있는 칸(NULL)이 있는 열에만 '결측 있음'을 붙여요. 0은 빈 칸이 아니에요!",
				"3단계는 형식 꼬리표예요. 한 열 안에서 값을 쓰는 모양이 다른 게 섞여 있으면 '형식 섞임'이에요."],
			"hints": ["표에서 열 하나를 세로로 쭉 읽어 보세요. 그 열의 값으로 무엇을 할지 생각하면 꼬리표가 보여요.", "숫자처럼 보여도 계산하지 않으면 문자예요. 0은 값이고, NULL만 결측이에요.", "joined 열을 위에서 아래로 읽어 보세요. 구분 기호가 다른 값이 있어요."]},
		"clean": {"id": "DATA01", "title": "기록 수리 공방", "levels": 3, "art": "DATA01", "npc": "NPC08", "npc_name": "기록 수리 담당자",
			"intro": ["시간 없어요, 얼른 도와줘요! 손님들 기록 카드가 엉망으로 섞여서 들어왔어요.",
				"왼쪽 선반에서 카드를 E로 한 장씩 집어서 알맞은 곳에 넣어 주세요. 빈 값이나 못 쓰는 값은 버림함, 이미 정리된 카드와 똑같으면 중복함, 모양이 틀렸으면 수리대예요.",
				"멀쩡한 카드는 오른쪽 투입구로! 투입구에 넣은 카드만 칠판의 정리된 표에 올라가요. 0은 빈 값이 아니라는 것도 잊지 말고요."],
			"talk": ["오늘은 빈 값만 골라내요. value 칸이 비어 있으면(NULL) 버림함, 나머지는 투입구로요. 0은 값이에요!",
				"이번엔 중복도 있어요. group과 value가 이미 정리된 카드와 똑같으면 중복함으로. 처음 나온 카드는 투입구로 보내야 해요.",
				"모양이 틀린 카드가 섞였어요. 공백, 쉼표, 슬래시가 있으면 수리대에서 먼저 고치고, 고친 카드를 다시 알맞은 곳에 넣어 주세요."],
			"hints": ["들고 있는 카드의 value 칸부터 보세요. 비어 있으면 버림함, 아니면 투입구예요.", "칠판에 이미 올라간 카드와 group·value를 비교해 보세요. 똑같으면 중복함이에요.", "' A '처럼 공백이 있거나 '1,000', '2026/01/05'처럼 모양이 다르면 수리대가 먼저예요. 'abc'처럼 고칠 수 없는 값은 버림함이에요."]},
		"stats": {"id": "DATA03", "title": "대표값 실험실", "levels": 3, "art": "DATA03", "npc": "NPC03", "npc_name": "통계 실험가",
			"intro": ["호호, 왔구나. 숫자 묶음을 값 하나로 요약하는 실험을 해 보자꾸나.",
				"먼저 위쪽 쟁반에서 숫자 블록을 E로 집어, 가운데 정렬 레일에 작은 수부터 왼쪽에서 차례로 꽂으렴. NULL 블록은 계산에서 빼니까 왼쪽 제외함에 넣고.",
				"정렬이 끝나면 오른쪽 선반에서 답 블록을 골라 평균·중앙값·범위 받침대에 올리렴. 평균은 합÷개수, 중앙값은 가운데 값, 범위는 최대-최소란다."],
			"talk": ["블록 네 개를 정렬하고 평균, 중앙값, 범위를 올려 보렴. 짝수 개면 가운데 두 값의 평균이 중앙값이야.",
				"홀수 개, 짝수 개, 그리고 NULL이 섞인 묶음이야. NULL은 개수에서도 빠진다는 걸 기억하렴.",
				"큰 값 하나가 끼면 평균과 중앙값이 어떻게 달라지는지 보고, 데이터로 말할 수 있는 결론 카드만 나에게 가져오렴."],
			"hints": ["작은 수부터 왼쪽에 꽂아요. 레일의 몇 번째 칸인지가 순서예요.", "평균 = 합 ÷ 개수, 중앙값 = 정렬한 뒤 가운데, 범위 = 최대 - 최소. NULL은 빼고 세요.", "[10,12,14,100]은 평균 34, 중앙값 13이에요. 평균만 크게 끌려 올라가요."]},
		"chart": {"id": "DATA04", "title": "차트 관측소", "levels": 3, "art": "DATA04", "npc": "NPC07", "npc_name": "차트 관측 담당자",
			"intro": ["좋아, 왔군. 차트는 예쁘게 그리는 게 아니라 질문에 답하려고 그리는 거다.",
				"가운데 대기대에서 데이터 카드를 E로 집어, 질문에 맞는 이젤에 꽂아라. 범주 비교는 막대, 시간 변화는 선, 두 수치의 관계는 산점도다. 빈 값이 있는 카드는 빈 값 상자로.",
				"차트가 다 그려지면 대기대에 결론 카드가 나온다. 차트가 보여 주는 것만 말하는 카드를 골라 왼쪽 질문 상자에 넣어라."],
			"talk": ["제품별 총판매량이다. 같은 제품 카드를 같은 막대에 꽂으면 위로 쌓여서 합계가 되지.",
				"월별 흐름이다. 선은 꽂는 순서대로 이어지니, 가장 이른 달부터 꽂아라.",
				"키와 몸무게의 관계다. 값이 빠진 카드는 점을 찍을 수 없어. 상관과 인과를 구분해라."],
			"hints": ["질문이 범주를 비교하는지, 시간 흐름을 보는지, 두 수치의 관계를 보는지 먼저 정하세요.", "같은 제품은 한 막대에 쌓여요. 월별 선은 1월, 2월, 3월 순서로 꽂아야 해요.", "차트에서 보이는 것만 말하는 결론을 고르세요. '원인'이라고 단정하면 틀려요."]},
	}

func problems_for(n: int) -> Array:
	match activity:
		"profile": return PROFILE_LEVELS[n]
		"clean": return CLEAN_LEVELS[n]
		"stats": return STAT_LEVELS[n]
	return CHART_LEVELS[n]

func setup_problem(p) -> void:
	match activity:
		"profile":
			goal = "선반의 %s 꼬리표를 들고 가 네 열에 붙이기" % p.lens
			state = {"held": "", "tags": {}}
		"clean":
			goal = p.goal
			state = {"queue": range(p.rows.size()), "held": [], "held_fixed": false, "kept": [], "bins": {"drop": [], "dup": []}}
		"stats":
			goal = "%s: %s" % [p.title, "블록을 작은 수부터 레일에 꽂기" if not p.values.is_empty() else "결론 카드를 실험가에게 가져가기"]
			var rail := []
			rail.resize(6)
			state = {"phase": "sort", "tray": p.values.duplicate(), "held": {}, "rail": rail, "excl": 0, "ans": {}}
			if p.values.is_empty():
				state.phase = "claim"
		"chart":
			goal = p.question
			state = {"phase": "cards", "taken": {}, "held": {}, "placed": [], "nulls": []}

func setup_level(n: int) -> void:
	super.setup_level(n)

func _ready() -> void:
	super._ready()
	# 로봇이 시안 위에 덧그린 표·게시판 뒤로 숨지 않게 앞에 그리고, 장치 표지는 로봇 발밑에 둔다
	player.z_index = 4
	plate_offset = Vector2(0, 30)
	hud.set_controls("WASD 이동 · E 집기/넣기 · F 힌트 · Z 되돌리기 · R 초기화 · H 도움말 · Esc 메뉴")

func handle(key: String) -> void:
	match activity:
		"profile": profile_action(key)
		"clean": clean_action(key)
		"stats": stats_action(key)
		"chart": chart_action(key)

func lab_rows() -> Array:
	match activity:
		"profile":
			# 열마다 붙인 꼬리표 (아직이면 _)
			var rows := []
			for c in PROFILE_TARGETS:
				rows.append([c, state.tags.get(c, "_")])
			return rows
		"clean":
			return [["남은 카드", state.queue.size()], ["정리된 표", state.kept.size()], ["버림함", state.bins.drop.size()], ["중복함", state.bins.dup.size()]]
		"stats":
			var p: Dictionary = problems()[problem]
			var out := [["문제", "%d / %d" % [problem + 1, problems().size()]]]
			for f in p.fields:
				out.append([STAT_LABELS[f], display(state.ans[f]) if state.ans.has(f) else "_"])
			return out
		"chart":
			var p: Dictionary = problems()[problem]
			return [["차트", p.type], ["꽂은 카드", state.placed.size()], ["빈 값 상자", state.nulls.size()]]
	return [["행동", moves], ["실수", mistakes], ["힌트", hints_used]]

func state_code() -> String:
	return ""

# ---------- 데이터 점검 ----------
func profile_action(key: String) -> void:
	var p: Dictionary = problems()[problem]
	if key.begins_with("take:"):
		var t := key.trim_prefix("take:")
		step()
		state.held = t
		say("'%s' 꼬리표를 들었어요. 표 아래 열 자리로 가져가 E로 붙이세요." % t, StageHUD.GOLD, 3.0)
		return
	if not key.begins_with("put:"):
		return
	var c := key.trim_prefix("put:")
	if state.held == "":
		say("먼저 오른쪽 선반에서 꼬리표를 E로 집어 오세요.", StageHUD.GOLD, 3.0)
		return
	step()
	if state.held != p.answer[c]:
		var t: String = state.held
		state.held = ""
		wrong("%s 열에 '%s'는 아니에요. 꼬리표는 선반으로 돌아갔어요." % [c, t])
		# 왜 틀렸는지는 담당자가 알림창으로 설명한다 (읽는 동안 멈춤)
		hud.start_dialogue(npc_name, npc_portrait, ["%s 열에 '%s' 꼬리표를 붙이면 분석팀이 헷갈려요.\n\n%s" % [c, t, p.why[c]]], "다시 해 보기")
		return
	state.tags[c] = state.held
	state.held = ""
	code(p.code[c], "%s → %s" % [c, p.answer[c]])
	if state.tags.size() < PROFILE_TARGETS.size():
		good("%s = %s, 맞아요! (%d / 4)" % [c, p.answer[c], state.tags.size()])
		return
	var note := {"자료형": "분석팀이 이제 우편번호를 더하지 않아요.", "결측": "age 결측 2/5 = 40%. 0은 값으로 남았어요.", "형식": "joined 의 2026/02/11 을 고치면 날짜로 바꿀 수 있어요."}
	win("%s 꼬리표 완료! %s 원본 표는 그대로예요." % [p.lens, note[p.lens]])


# ---------- 공통: 들고 다니는 물건 ----------
## 틀리면 담당자가 알림창으로 이유를 설명한다 (읽는 동안 멈춤). 들고 있던 물건은 그대로 둔다.
func explain(short: String, why: String) -> void:
	wrong(short)
	hud.start_dialogue(npc_name, npc_portrait, [why], "다시 해 보기")

func empty_hand_msg(where: String) -> void:
	say("먼저 %s에서 E로 집어 오세요." % where, StageHUD.GOLD, 3.0)

# ---------- 데이터 정제 (DA-02) ----------
func valid_date(t: String) -> bool:
	var parts = t.split("-")
	if parts.size() != 3 or not parts[1].is_valid_int() or not parts[2].is_valid_int():
		return false
	return int(parts[1]) >= 1 and int(parts[1]) <= 12 and int(parts[2]) >= 1 and int(parts[2]) <= 31

func card_text(r: Array) -> String:
	return "#%d  %s  %s  %s" % [r[0], "'%s'" % r[1] if str(r[1]) != str(r[1]).strip_edges() else str(r[1]), display(r[2]), r[3]]

func needs_repair(r: Array) -> bool:
	return str(r[1]) != str(r[1]).strip_edges() or (r[2] != null and str(r[2]).contains(",")) or str(r[3]).contains("/")

func repaired(r: Array) -> Array:
	return [r[0], str(r[1]).strip_edges(), str(r[2]).replace(",", "") if r[2] != null else null, str(r[3]).replace("/", "-")]

func unusable(r: Array) -> bool:
	if r[2] == null:
		return true
	return not str(r[2]).replace(",", "").is_valid_float() or not valid_date(str(r[3]).replace("/", "-"))

func dedup_key(r: Array, mode: String) -> String:
	if mode == "group+value":
		return "%s|%s" % [r[1], r[2]]
	return "%s|%s|%s" % [r[1], r[2], r[3]]

func dup_of(r: Array) -> int:
	var mode: String = problems()[problem].dedup
	if mode == "":
		return -1
	for k in state.kept:
		if dedup_key(k, mode) == dedup_key(r, mode):
			return k[0]
	return -1

## 들고 있는 카드가 가야 할 곳: drop(버림) / fix(수리) / dup(중복) / keep(투입구)
func clean_dest(r: Array) -> String:
	if unusable(r):
		return "drop"
	if needs_repair(r):
		return "fix"
	if dup_of(r) >= 0:
		return "dup"
	return "keep"

func clean_why(r: Array, want: String, got: String) -> String:
	match want:
		"drop":
			if r[2] == null:
				return "카드 #%d는 value 칸이 비어 있어요(NULL). 빈 값 기록은 버림함으로 보내요." % r[0]
			if not str(r[2]).replace(",", "").is_valid_float():
				return "'%s'는 숫자로 고칠 수 없는 값이에요. 수리대에서도 못 고치니까 버림함으로 보내요." % r[2]
			return "'%s'는 13월 40일이라 세상에 없는 날짜예요. 고칠 수 없으니 버림함으로 보내요." % r[3]
		"fix":
			return "카드 #%d는 모양이 섞여 있어요(앞뒤 공백, 쉼표, 슬래시). 이대로 두면 같은 값인지 비교할 수 없어요. 수리대에서 먼저 고쳐 주세요." % r[0]
		"dup":
			return "칠판에 이미 올라간 카드 #%d와 %s가 똑같아요. 처음 나온 카드만 남기고 이 카드는 중복함으로 보내요." % [dup_of(r), "group·value" if problems()[problem].dedup == "group+value" else "id 빼고 모든 칸"]
	match got:
		"drop":
			return "카드 #%d는 value가 %s로 채워져 있어요. 0도 엄연한 값이라 버리면 안 돼요. 투입구로 보내 주세요." % [r[0], display(r[2])] if str(r[2]) == "0" else "카드 #%d는 빈 칸도, 못 쓰는 값도 없어요. 투입구로 보내 주세요." % r[0]
		"dup":
			return "칠판에 카드 #%d와 똑같은 카드가 아직 없어요. 처음 나온 카드는 투입구로 보내야 해요." % r[0]
		"fix":
			return "카드 #%d는 고칠 곳이 없어요. 바로 투입구로 보내 주세요." % r[0]
	return ""

const CLEAN_CODE := {"drop": "df = df.drop(index=%d)  # 빈 값·못 쓰는 값", "dup": "df = df.drop(index=%d)  # 중복", "keep": "clean.append(row %d)"}

func clean_action(key: String) -> void:
	var p: Dictionary = problems()[problem]
	if key == "take":
		if not state.held.is_empty() or state.queue.is_empty():
			return
		step()
		state.held = p.rows[state.queue.pop_front()].duplicate()
		state.held_fixed = false
		say("카드 %s 를 들었어요. 알맞은 곳으로 가져가 E로 넣으세요." % card_text(state.held), StageHUD.GOLD, 3.0)
		return
	if not key.begins_with("put:"):
		return
	if state.held.is_empty():
		empty_hand_msg("왼쪽 선반")
		return
	var got := key.trim_prefix("put:")
	var r: Array = state.held
	var want := clean_dest(r)
	step()
	if got != want:
		explain("카드 #%d는 %s가 아니에요." % [r[0], CLEAN_BINS[got]], clean_why(r, want, got))
		return
	match got:
		"fix":
			state.held = repaired(r)
			state.held_fixed = true
			code("df.loc[%d] = %s  # 공백·쉼표·슬래시 정리" % [r[0], str(state.held.slice(1))])
			good("수리 완료! 고친 카드를 다시 알맞은 곳에 넣으세요.")
			return
		"keep":
			state.kept.append(r)
		_:
			state.bins[got].append(r[0])
	code(CLEAN_CODE[got] % r[0])
	state.held = []
	if not state.queue.is_empty():
		good("카드 #%d → %s, 맞아요!" % [r[0], CLEAN_BINS[got]])
		return
	win("정리 완료! 원본 %d장 중 %d장이 깨끗한 표가 됐어요. (버림 %d · 중복 %d)" % [p.rows.size(), state.kept.size(), state.bins.drop.size(), state.bins.dup.size()])

# ---------- 대표값 (DA-03) ----------
func sorted_nums(values: Array) -> Array:
	var out = values.filter(func(v): return v != null)
	out.sort()
	return out

func stat(name: String, values: Array) -> float:
	var v = sorted_nums(values)
	if v.is_empty():
		return NAN
	match name:
		"mean":
			var total = 0.0
			for x in v:
				total += x
			return total / v.size()
		"median":
			var n = v.size()
			return float(v[n / 2]) if n % 2 == 1 else (v[n / 2 - 1] + v[n / 2]) / 2.0
		"range":
			return float(v.back()) - float(v[0])
	return NAN

func stat_why(p: Dictionary, f: String, got: float) -> String:
	var v = sorted_nums(p.values)
	var total = 0.0
	for x in v:
		total += x
	match f:
		"mean":
			return "%s는 평균이 아니에요.\n\n평균 = 합 ÷ 개수 = %s ÷ %d = %s 예요.%s" % [display(got), display(total), v.size(), display(stat("mean", p.values)), " NULL은 개수에서도 빠져요." if p.values.has(null) else ""]
		"median":
			var n: int = v.size()
			var mid := "가운데 값 %s" % display(v[n / 2]) if n % 2 == 1 else "가운데 두 값 %s, %s의 평균 %s" % [display(v[n / 2 - 1]), display(v[n / 2]), display(stat("median", p.values))]
			return "%s는 중앙값이 아니에요.\n\n정렬하면 %s 이고, %s이 중앙값이에요." % [display(got), str(v.map(func(x): return display(x))), mid]
	return "%s는 범위가 아니에요.\n\n범위 = 최대 - 최소 = %s - %s = %s 예요." % [display(got), display(v.back()), display(v[0]), display(stat("range", p.values))]

func stats_phase_after_sort() -> void:
	var p: Dictionary = problems()[problem]
	if not p.fields.is_empty():
		state.phase = "answer"
		good("정렬 완료! 이제 오른쪽 선반의 답 블록을 받침대에 올리세요.")
	elif p.has("claims"):
		state.phase = "claim"
		good("이제 결론 카드를 골라 실험가에게 가져가세요.")

func stats_action(key: String) -> void:
	var p: Dictionary = problems()[problem]
	var held: Dictionary = state.held
	if key == "tray":
		if not held.is_empty() or state.tray.is_empty():
			return
		step()
		state.held = {"t": "data", "v": state.tray.pop_front()}
		say("%s 블록을 들었어요. %s" % [display(state.held.v), "NULL은 제외함으로!" if state.held.v == null else "레일의 알맞은 칸에 꽂으세요."], StageHUD.GOLD, 3.0)
		return
	if key.begins_with("shelf:"):
		if not held.is_empty():
			return
		step()
		state.held = {"t": "answer", "v": p.choices[int(key.trim_prefix("shelf:"))]}
		say("%s 블록을 들었어요. 맞는 받침대에 올리세요." % display(state.held.v), StageHUD.GOLD, 3.0)
		return
	if key.begins_with("claim:"):
		if not held.is_empty():
			return
		step()
		state.held = {"t": "claim", "v": int(key.trim_prefix("claim:"))}
		say("결론 카드를 들었어요. 실험가에게 가져가세요.", StageHUD.GOLD, 3.0)
		return
	if held.is_empty():
		empty_hand_msg({"answer": "오른쪽 선반", "claim": "오른쪽 선반의 결론 카드"}.get(state.phase, "위쪽 쟁반"))
		return
	var s = sorted_nums(p.values)
	if key.begins_with("rail:"):
		var i := int(key.trim_prefix("rail:"))
		step()
		if held.v == null:
			explain("NULL은 레일에 꽂지 않아요.", "NULL은 값이 없다는 표시예요. 크기를 비교할 수 없으니 정렬에도, 평균의 개수에도 넣지 않아요. 왼쪽 제외함에 넣어 주세요.")
			return
		if s[i] != held.v:
			var rank := s.find(held.v)
			explain("%s는 %d번째 칸이 아니에요." % [display(held.v), i + 1], "작은 수부터 왼쪽에 꽂아요. 이 묶음을 정렬하면 %s 이라서, %s는 왼쪽에서 %d번째 칸이에요." % [str(s.map(func(x): return display(x))), display(held.v), rank + 1])
			return
		state.rail[i] = held.v
		state.held = {}
		code("sorted_values[%d] = %s" % [i, display(s[i])])
		if state.tray.is_empty():
			stats_phase_after_sort()
		else:
			good("%s → %d번째 칸, 맞아요!" % [display(s[i]), i + 1])
		return
	if key == "exclude":
		step()
		if held.v != null:
			explain("%s는 빼지 않아요." % display(held.v), "제외함에는 값이 없는 NULL만 넣어요. %s는 진짜 값이니 레일에 꽂아 주세요." % display(held.v))
			return
		state.excl += 1
		state.held = {}
		code("values = values.dropna()", "NULL 제외")
		if state.tray.is_empty():
			stats_phase_after_sort()
		else:
			good("NULL → 제외함, 맞아요!")
		return
	if key.begins_with("ped:"):
		var f := key.trim_prefix("ped:")
		step()
		var want := stat(f, p.values)
		if absf(float(held.v) - want) > 0.01:
			state.held = {}   # 답 블록은 선반으로 돌아간다
			explain("%s는 %s이 아니에요." % [display(held.v), STAT_LABELS[f]], stat_why(p, f, float(held.v)))
			return
		state.ans[f] = held.v
		state.held = {}
		code("values.%s()  # = %s" % [f, display(want)])
		if state.ans.size() < p.fields.size():
			good("%s = %s, 맞아요!" % [STAT_LABELS[f], display(want)])
			return
		if p.has("claims"):
			state.phase = "claim"
			good("%s = %s! 이제 결론 카드를 골라 실험가에게 가져가세요." % [STAT_LABELS[f], display(want)])
			return
		finish_problem("%s 실험 완료! 계산이 데이터와 맞아요." % p.title)
		return
	if key == "npc":
		step()
		if held.v != p.answer:
			state.held = {}
			explain("그 결론은 데이터로 말할 수 없어요.", "'%s'\n\n이 말은 숫자가 보여 주는 것보다 더 나가 버렸어요. 값만 보고 확실히 말할 수 있는 카드를 골라 주세요." % p.claims[held.v])
			return
		state.held = {}
		code("# 결론: " + p.claims[p.answer])
		finish_problem("%s: 데이터로 말할 수 있는 결론이에요." % p.title)

# ---------- 차트 (DA-04) ----------
func chart_card_text(r: Array, p: Dictionary) -> String:
	if p.type == "산점도":
		return "%s %s\n%s %s" % [p.cols[0], display(r[0]), p.cols[1], display(r[1])]
	return "%s\n%s%s" % [display(r[0]), display(r[1]), p.units[1] if r[1] != null else ""]

func has_null(r: Array) -> bool:
	return r[0] == null or r[1] == null

func chart_left(p: Dictionary) -> Array:
	var out := []
	for i in p.rows.size():
		if not state.taken.has(i):
			out.append(i)
	return out

func chart_cards_done(p: Dictionary) -> bool:
	return chart_left(p).is_empty() and state.held.is_empty()

func chart_action(key: String) -> void:
	var p: Dictionary = problems()[problem]
	var held: Dictionary = state.held
	if key.begins_with("card:"):
		var i := int(key.trim_prefix("card:"))
		if not held.is_empty() or state.taken.has(i):
			return
		step()
		state.taken[i] = true
		state.held = {"t": "card", "i": i}
		say("카드 '%s'를 들었어요. 질문에 맞는 이젤에 꽂거나, 빈 값이면 빈 값 상자에 넣으세요." % chart_card_text(p.rows[i], p).replace("\n", " "), StageHUD.GOLD, 3.0)
		return
	if key.begins_with("claim:"):
		if not held.is_empty():
			return
		step()
		state.held = {"t": "claim", "i": int(key.trim_prefix("claim:"))}
		say("결론 카드를 들었어요. 왼쪽 질문 상자에 넣으세요.", StageHUD.GOLD, 3.0)
		return
	if held.is_empty():
		empty_hand_msg("가운데 대기대")
		return
	if key == "question":
		step()
		state.held = {}
		if held.i != p.answer:
			explain("그 결론은 차트가 보여 주지 않아요.", "'%s'\n\n차트는 값의 크기와 흐름만 보여 줘요. 원인이나 중요도는 차트만으로 말할 수 없어요. 차트에 보이는 것만 말하는 카드를 골라 주세요." % p.claims[held.i])
			return
		code("# 결론: " + p.claims[p.answer])
		win("차트로 질문에 답했어요! %s" % p.claims[p.answer])
		return
	var r: Array = p.rows[held.i]
	if key == "nullbox":
		step()
		if not has_null(r):
			explain("빈 값이 없는 카드예요.", "이 카드는 두 값이 다 있어요. 빈 값 상자에는 값이 빠진 카드만 넣어요. 이젤에 꽂아 주세요.")
			return
		state.nulls.append(held.i)
		state.held = {}
		code("df = df.dropna()  # 빈 값 카드 제외")
		chart_after_card(p, "빈 값 카드 → 빈 값 상자, 맞아요!")
		return
	if key.begins_with("easel:"):
		var e := int(key.trim_prefix("easel:"))
		step()
		if has_null(r):
			explain("빈 값이 있는 카드는 그릴 수 없어요.", "이 카드는 값 하나가 비어 있어요. 점이나 막대를 어디에 그릴지 정할 수 없으니 가운데 아래 빈 값 상자에 넣어 주세요.")
			return
		if CHART_TYPES[e] != p.type:
			var why := {"막대": "제품처럼 이름(범주)끼리 크기를 비교할 때는 막대 차트예요.", "선": "달마다 어떻게 변하는지(시간 흐름)를 볼 때는 선 차트예요.", "산점도": "키와 몸무게처럼 두 숫자의 관계를 볼 때는 산점도예요."}
			explain("%s 차트가 아니에요." % CHART_TYPES[e], "질문: %s\n\n%s" % [p.question, why[p.type]])
			return
		if p.type == "선":
			var earliest := str(r[0])
			for j in chart_left(p):
				if not has_null(p.rows[j]) and str(p.rows[j][0]) < earliest:
					earliest = str(p.rows[j][0])
			if earliest != str(r[0]):
				explain("%s보다 이른 달이 남아 있어요." % r[0], "선 차트는 꽂는 순서대로 이어져요. 시간 흐름이 보이려면 가장 이른 달(%s)부터 꽂아야 해요." % earliest)
				return
		state.placed.append(held.i)
		state.held = {}
		code("chart.add(%s, %s)" % [display(r[0]), display(r[1])])
		chart_after_card(p, "%s 차트에 꽂았어요!" % p.type)

func chart_after_card(p: Dictionary, msg: String) -> void:
	if chart_cards_done(p):
		state.phase = "claim"
		good("차트 완성! 대기대에 나온 결론 카드를 골라 질문 상자에 넣으세요.")
	else:
		good(msg)

## 막대: 범주별 합계 (처음 꽂은 순서), 선·산점도: 꽂은 순서 그대로
func chart_series(p: Dictionary) -> Array:
	var out := []
	if p.type != "막대":
		for i in state.placed:
			out.append(p.rows[i])
		return out
	var order := []
	var sums := {}
	for i in state.placed:
		var k = p.rows[i][0]
		if not sums.has(k):
			order.append(k)
			sums[k] = 0.0
		sums[k] += float(p.rows[i][1])
	for k in order:
		out.append([k, sums[k]])
	return out


# ---------- 시안 위 배치 ----------
func stations() -> Array:
	match activity:
		"profile": return profile_stations()
		"clean": return clean_stations()
		"stats": return stats_stations()
	return chart_stations()

func profile_stations() -> Array:
	# St0~2: 선반 꼬리표, St3~6: 표 아래 열 자리 (표지는 draw_profile_board 가 직접 그린다)
	var p: Dictionary = problems()[problem]
	var out := []
	for i in 3:
		out.append(["take:" + p.tags[i], "'%s' 꼬리표 집기" % p.tags[i], ""] if i < p.tags.size() else null)
	for c in PROFILE_TARGETS:
		if state.tags.has(c):
			out.append(null)
		elif state.held != "":
			out.append(["put:" + c, "%s 열에 '%s' 붙이기" % [c, state.held], ""])
		else:
			out.append(["put:" + c, "%s 열 자리 (꼬리표를 먼저 집어 오세요)" % c, ""])
	return out


func clean_stations() -> Array:
	# St0 선반, St1 버림함, St2 중복함, St3 수리대, St4 투입구
	var holding: bool = not state.held.is_empty()
	var out: Array = []
	out.append(["take", "카드 집기 (남은 %d장)" % state.queue.size(), ""] if not holding and not state.queue.is_empty() else null)
	for k in ["drop", "dup", "fix", "keep"]:
		out.append(["put:" + k, "%s에 넣기" % CLEAN_BINS[k], ""] if holding else ["put:" + k, "%s (카드를 먼저 집어 오세요)" % CLEAN_BINS[k], ""])
	return out

func stats_stations() -> Array:
	# St0 쟁반, St1~6 레일, St7 제외함, St8~10 받침대, St11~18 답 선반, St19~21 결론 카드, St22 실험가
	var p: Dictionary = problems()[problem]
	var held: Dictionary = state.held
	var s = sorted_nums(p.values)
	var out: Array = []
	var sorting: bool = state.phase == "sort"
	out.append(["tray", "숫자 블록 집기 (남은 %d개)" % state.tray.size(), ""] if sorting and held.is_empty() and not state.tray.is_empty() else null)
	for i in 6:
		out.append(["rail:%d" % i, "레일 %d번째 칸에 꽂기" % (i + 1), ""] if sorting and held.get("t", "") == "data" and i < s.size() and state.rail[i] == null else null)
	out.append(["exclude", "제외함에 넣기", ""] if sorting and held.get("t", "") == "data" else null)
	for f in STAT_FIELDS:
		out.append(["ped:" + f, "%s 받침대에 올리기" % STAT_LABELS[f], ""] if state.phase == "answer" and held.get("t", "") == "answer" and p.fields.has(f) and not state.ans.has(f) else null)
	for j in 8:
		out.append(["shelf:%d" % j, "%s 블록 집기" % display(p.choices[j]), ""] if state.phase == "answer" and held.is_empty() and j < p.choices.size() else null)
	var claims: Array = p.get("claims", [])
	for c in 3:
		out.append(["claim:%d" % c, "결론 카드 %d 집기" % (c + 1), ""] if state.phase == "claim" and held.is_empty() and c < claims.size() else null)
	out.append(["npc", "실험가에게 결론 카드 건네기", ""] if held.get("t", "") == "claim" else null)
	return out

func chart_stations() -> Array:
	# St0~2 이젤(막대·선·산점도), St3~8 대기대 카드, St9 빈 값 상자, St10~12 결론 카드, St13 질문 상자
	var p: Dictionary = problems()[problem]
	var held: Dictionary = state.held
	var out: Array = []
	for e in 3:
		out.append(["easel:%d" % e, "%s 이젤에 꽂기" % CHART_TYPES[e], ""] if held.get("t", "") == "card" else null)
	for i in 6:
		out.append(["card:%d" % i, "카드 집기: %s" % chart_card_text(p.rows[i], p).replace("\n", " "), ""] if state.phase == "cards" and held.is_empty() and i < p.rows.size() and not state.taken.has(i) else null)
	out.append(["nullbox", "빈 값 상자에 넣기", ""] if held.get("t", "") == "card" else null)
	for c in 3:
		out.append(["claim:%d" % c, "결론 카드 %d 집기" % (c + 1), ""] if state.phase == "claim" and held.is_empty() and c < p.claims.size() else null)
	out.append(["question", "질문 상자에 결론 넣기", ""] if held.get("t", "") == "claim" else null)
	return out

func draw_board() -> void:
	match activity:
		"profile": draw_profile_board()
		"clean": draw_clean_board()
		"stats": draw_stats_board()
		"chart": draw_chart_board()


const TAG_FILES := {"숫자": "number", "문자": "text", "날짜": "date", "결측 있음": "missing_yes", "결측 없음": "missing_no", "형식 OK": "format_ok", "형식 섞임": "format_mixed"}
const TAG_DIR := "res://textures/stages/DATA02/tags/"
const HOOK_Y := 252.0   # 붙인 꼬리표: 화면 안, 열 머리 바로 위 칸 중심
const TABLE_Y := 268.0
const ROW_H := 36.0
const SLOT_Y := 545.0   # 표 아래 받침대 중심
var _tex_cache := {}

func _tex(name: String) -> Texture2D:
	if not _tex_cache.has(name):
		_tex_cache[name] = load(TAG_DIR + name + ".png")
	return _tex_cache[name]

## 꼬리표 그림 한 장. c = 중심, w = 폭. 글씨는 오른쪽 빈 칸에 쓴다.
func tag_sprite(c: Vector2, tag: String, w: float, size := 0) -> void:
	var tex := _tex("tag_" + TAG_FILES.get(tag, "number"))
	var h := w * 110.0 / 240.0
	_cv.draw_texture_rect(tex, Rect2(c - Vector2(w, h) / 2, Vector2(w, h)), false)
	if size > 0:
		var tx := c.x + w * 0.17
		var s := fit_size(tag, w * 0.58, size)
		text(Vector2(tx, c.y + s * 0.36), tag, s, INK, true)

func col_x(ci: int) -> float:
	return 382 + 344.0 / PROFILE_COLS.size() * (ci + 0.5)

func draw_profile_board() -> void:
	var p: Dictionary = problems()[problem]
	table_at(Vector2(382, TABLE_Y), PROFILE_COLS, PROFILE_ROWS, 344, ROW_H, 17)
	wrapped(Vector2(172, 336), "데이터 사전\n1행 = 학생 1명\nage 나이(세)\nzip 우편번호\njoined 가입일\nvisits 방문 수(회)\nNULL = 빈 칸", 150, 16, INK)
	text(Vector2(1004, 332), "%d단계 · %s 점검" % [level + 1, p.lens], 19, INK, true)
	# 붙인 꼬리표: 표 화면 안, 그 열 머리 바로 위
	for c in state.tags:
		tag_sprite(Vector2(col_x(PROFILE_COLS.find(c)), HOOK_Y), state.tags[c], 68, 13)
	# 오른쪽 선반 고리의 꼬리표
	for i in 3:
		var sp = spot("st", i)
		if sp == null or i >= p.tags.size() or state.held == p.tags[i]:
			continue
		var focused: bool = player.focus == sp
		tag_sprite(sp.position + Vector2(0, 2), p.tags[i], 112 if focused else 100, 15)
	# 표 아래 받침대: 가까이 가면 노랗게, 붙이면 초록으로. 받침대가 가리키는 열을 표에 칠한다.
	var cw := 344.0 / PROFILE_COLS.size()
	for k in PROFILE_TARGETS.size():
		var c: String = PROFILE_TARGETS[k]
		var sp = spot("st", 3 + k)
		var x := col_x(PROFILE_COLS.find(c))
		var col_rect := Rect2(x - cw / 2, TABLE_Y, cw, ROW_H * 6)
		var name := ""
		var focused: bool = sp != null and player.focus == sp
		if state.tags.has(c):
			name = "slot_done"
			_cv.draw_rect(col_rect, Color(0.45, 0.85, 0.5, 0.28))
			_cv.draw_rect(col_rect, Color("2f9e4a"), false, 3.0)
		elif focused:
			name = "slot_ready"
			_cv.draw_rect(col_rect, Color(1.0, 0.82, 0.25, 0.30))
			_cv.draw_rect(col_rect.grow(1), INK, false, 6.0)
			_cv.draw_rect(col_rect, Color("ffc928"), false, 4.0)
		if name != "":
			_cv.draw_texture_rect(_tex(name), Rect2(Vector2(x, SLOT_Y) - Vector2(32, 24), Vector2(64, 48)), false)
		# 표와 받침대 사이 열 이름 (받침대가 어느 열인지)
		plate(Vector2(x, 500), state.tags[c] if state.tags.has(c) else "▼ " + c, 14, Color("9fe0a8") if state.tags.has(c) else (GOLD if focused else CREAM), INK, 60)
	# 들고 있는 꼬리표: 로봇 머리 위
	if state.held != "":
		tag_sprite(player.position + Vector2(78, -46), state.held, 120, 17)


# ---------- 카드·블록 그림 (GPT 그림이 있으면 그림, 없으면 임시 상자) ----------
const SHARED_DIR := "res://textures/stages/DATA_shared/"

func shared_tex(name: String) -> Texture2D:
	var key := "shared_" + name
	if not _tex_cache.has(key):
		var path := SHARED_DIR + name + ".png"
		_tex_cache[key] = load(path) if ResourceLoader.exists(path) else null
	return _tex_cache[key]

func held_pos() -> Vector2:
	return player.position + Vector2(96, -48)

## 종이 카드. kind = card_data / card_fixed / card_claim
func card_box(c: Vector2, w: float, h: float, t: String, size: int, kind := "card_data", glow := false) -> void:
	var r := Rect2(c - Vector2(w, h) / 2, Vector2(w, h))
	if glow:
		_cv.draw_rect(r.grow(5), GOLD)
	var tex := shared_tex(kind)
	if tex != null:
		_cv.draw_texture_rect(tex, r, false)
	else:
		_cv.draw_rect(r, INK)
		_cv.draw_rect(r.grow(-2), CREAM if kind != "card_fixed" else Color("e4f6e0"))
		_cv.draw_rect(Rect2(r.position + Vector2(2, 2), Vector2(7, h - 4)), {"card_data": BLUE, "card_fixed": TEAL, "card_claim": RED}[kind])
	if kind == "card_claim":
		wrapped(r.position + Vector2(10, size + 6), t, w - 18, size, INK)
		return
	var lines := t.split("\n")
	for i in lines.size():
		var s := fit_size(lines[i], w - 14, size)
		text(Vector2(c.x + 3, c.y + s * 0.36 + (i - (lines.size() - 1) / 2.0) * (size + 3)), lines[i], s, INK, true)

## 숫자 블록. v == null 이면 빈 값 블록
func block_box(c: Vector2, s: float, v, glow := false) -> void:
	var r := Rect2(c - Vector2(s, s) / 2, Vector2(s, s))
	if glow:
		_cv.draw_rect(r.grow(4), GOLD)
	var tex := shared_tex("block_null" if v == null else "block_value")
	if tex != null:
		_cv.draw_texture_rect(tex, r, false)
	else:
		_cv.draw_rect(r, INK)
		_cv.draw_rect(r.grow(-2), Color("c9c5bb") if v == null else Color("f4d58d"))
	var t := "NULL" if v == null else display(v)
	var fs := fit_size(t, s, int(s * 0.42))
	text(Vector2(c.x, c.y + fs * 0.36), t, fs, Color(0.3, 0.3, 0.3) if v == null else INK, true)

func label(c: Vector2, t: String, size := 16, focused := false, done_ := false) -> void:
	plate(c, t, size, Color("9fe0a8") if done_ else (GOLD if focused else CREAM))

func focused_key(i: int) -> bool:
	var sp = spot("st", i)
	return sp != null and player.focus == sp

# ---------- DA-02 기록 수리 공방 ----------
const CLEAN_POS := {"take": Vector2(274, 362), "drop": Vector2(475, 396), "dup": Vector2(638, 396), "fix": Vector2(802, 396), "keep": Vector2(1006, 452)}

func draw_clean_board() -> void:
	var p: Dictionary = problems()[problem]
	# 왼쪽 선반: 남은 카드 더미 (맨 위 카드만 글씨)
	var n: int = state.queue.size()
	for k in range(mini(n, 3) - 1, -1, -1):
		var r: Array = p.rows[state.queue[k]]
		card_box(CLEAN_POS.take + Vector2(k * 6, -k * 14), 200, 46, card_text(r) if k == 0 else "", 15, "card_data", k == 0 and focused_key(0))
	label(CLEAN_POS.take + Vector2(0, 62), "남은 카드 %d장" % n, 15)
	# 기계 앞 이름판과 들어간 카드 번호
	var names := ["drop", "dup", "fix"]
	for i in names.size():
		var k: String = names[i]
		label(CLEAN_POS[k], CLEAN_BINS[k], 17, focused_key(1 + i) and not state.held.is_empty())
		if k != "fix" and not state.bins[k].is_empty():
			plate(CLEAN_POS[k] + Vector2(0, 40), " ".join(state.bins[k].map(func(x): return "#%d" % x)), 14, Color("ffd7a8"))
	label(CLEAN_POS.keep, "투입구", 17, focused_key(4) and not state.held.is_empty())
	# 오른쪽 칠판: 투입구로 들어간 카드만 정리된 표에 쌓인다
	var y := 248.0
	text(Vector2(924, y), "정리된 표 (%d행)" % state.kept.size(), 16, Color("ffe9a8"))
	text(Vector2(924, y + 21), "id  group  value  date", 13, Color("cfe3ff"))
	for i in state.kept.size():
		var r: Array = state.kept[i]
		text(Vector2(924, y + 40 + i * 18), "%d   %s   %s   %s" % [r[0], r[1], display(r[2]), r[3]], 13, Color.WHITE)
	if not state.held.is_empty():
		card_box(held_pos(), 200, 46, card_text(state.held), 15, "card_fixed" if state.held_fixed else "card_data")

# ---------- DA-03 대표값 실험실 ----------
const TRAY_X := [365.0, 397.0, 430.0, 463.0, 495.0, 527.0]
const REF_X := [646.0, 678.0, 711.0, 744.0, 776.0, 807.0]
const RAIL_X := [338.0, 426.0, 514.0, 602.0, 690.0, 776.0]
const PED_X := {"mean": 313.0, "median": 530.0, "range": 747.0}
const SHELF_POS := [Vector2(944, 347), Vector2(1007, 347), Vector2(1071, 347), Vector2(1134, 347), Vector2(944, 446), Vector2(1007, 446), Vector2(1071, 446), Vector2(1134, 446)]
const CLAIM_Y3 := [336.0, 397.0, 458.0]   # 선반 자리에 가로로 긴 결론 카드 3장

func draw_stats_board() -> void:
	var p: Dictionary = problems()[problem]
	var s = sorted_nums(p.values)
	for i in state.tray.size():
		block_box(Vector2(TRAY_X[i], 241), 32, state.tray[i], i == 0 and focused_key(0))
	if p.has("ref"):
		for i in p.ref.size():
			block_box(Vector2(REF_X[i], 241), 32, p.ref[i])
		plate(Vector2(732, 292), "비교 집단 · 평균 10", 13, Color("e6e0d0"))
	# 정렬 레일
	for i in s.size():
		if state.rail[i] != null:
			block_box(Vector2(RAIL_X[i], 358), 46, state.rail[i])
		else:
			var hl: bool = state.held.get("t", "") == "data" and focused_key(1 + i)
			_cv.draw_rect(Rect2(RAIL_X[i] - 22, 336, 44, 44), GOLD if hl else Color(1, 1, 1, 0.35), false, 3.0)
		text(Vector2(RAIL_X[i], 398), "%d" % (i + 1), 13, WOOD, true)
	if state.phase != "sort" and not s.is_empty():
		plate(Vector2(RAIL_X[mini(s.size(), 5)] + (60 if s.size() >= 6 else 0), 358), "개수 %d" % s.size(), 14, Color("e6e0d0"))
	label(Vector2(191, 410), "제외함" + (" · NULL %d" % state.excl if state.excl > 0 else ""), 14, focused_key(7) and state.held.get("t", "") == "data")
	# 받침대
	for i in STAT_FIELDS.size():
		var f: String = STAT_FIELDS[i]
		var used: bool = p.fields.has(f)
		plate(Vector2(PED_X[f], 538), STAT_LABELS[f], 17, Color("9fe0a8") if state.ans.has(f) else (GOLD if focused_key(8 + i) and state.held.get("t", "") == "answer" else (CREAM if used else Color("cfc8b8"))), INK if used else Color(0.45, 0.42, 0.38))
		if state.ans.has(f):
			block_box(Vector2(PED_X[f], 486), 50, state.ans[f])
	# 오른쪽 선반: 답 블록 또는 결론 카드
	if state.phase == "claim":
		for c in p.claims.size():
			card_box(Vector2(1041, CLAIM_Y3[c]), 244, 56, "%d. %s" % [c + 1, p.claims[c]], 13, "card_claim", focused_key(19 + c))
	elif not p.choices.is_empty():
		for j in p.choices.size():
			block_box(SHELF_POS[j], 52, p.choices[j], state.phase == "answer" and focused_key(11 + j))
			if state.phase == "sort":
				_cv.draw_rect(Rect2(SHELF_POS[j] - Vector2(26, 26), Vector2(52, 52)), Color(0.2, 0.2, 0.25, 0.45))
	var held: Dictionary = state.held
	if held.get("t", "") == "claim":
		card_box(held_pos() + Vector2(10, -20), 150, 110, p.claims[held.v], 12, "card_claim")
	elif not held.is_empty():
		block_box(held_pos() + Vector2(-30, 0), 48, held.v)

# ---------- DA-04 차트 관측소 ----------
const CARD_POS := [Vector2(558, 374), Vector2(641, 374), Vector2(724, 374), Vector2(558, 424), Vector2(641, 424), Vector2(724, 424)]
const EASEL_AREA := [Rect2(300, 145, 140, 92), Rect2(570, 145, 146, 92), Rect2(858, 145, 136, 92)]
const EASEL_X := [368.0, 631.0, 917.0]

func draw_chart_board() -> void:
	var p: Dictionary = problems()[problem]
	var held: Dictionary = state.held
	var carrying: bool = held.get("t", "") == "card"
	for e in 3:
		label(Vector2(EASEL_X[e], 266), CHART_TYPES[e], 16, carrying and focused_key(e))
	draw_chart_marks(p, EASEL_AREA[CHART_TYPES.find(p.type)])
	if state.phase == "cards":
		for i in p.rows.size():
			if not state.taken.has(i):
				card_box(CARD_POS[i], 78, 44, chart_card_text(p.rows[i], p), 13, "card_data", focused_key(3 + i))
	else:
		for c in p.claims.size():
			if held.get("t", "") == "claim" and held.i == c:
				continue
			card_box(Vector2(641, 357 + c * 41), 256, 38, "%d. %s" % [c + 1, p.claims[c]], 12, "card_claim", focused_key(10 + c))
	label(Vector2(631, 594), "빈 값 상자" + (" · %d장" % state.nulls.size() if not state.nulls.is_empty() else ""), 14, carrying and focused_key(9))
	wrapped(Vector2(246, 408), p.question, 112, 12, INK)
	label(Vector2(317, 498), "질문 상자", 14, held.get("t", "") == "claim" and focused_key(13))
	if carrying:
		card_box(held_pos(), 100, 48, chart_card_text(p.rows[held.i], p), 14)
	elif held.get("t", "") == "claim":
		card_box(held_pos() + Vector2(10, -20), 150, 110, p.claims[held.i], 12, "card_claim")

func draw_chart_marks(p: Dictionary, area: Rect2) -> void:
	var data := chart_series(p)
	if data.is_empty():
		return
	# 눈금이 카드마다 바뀌지 않게, 다 꽂았을 때 기준으로 축을 잡는다
	var full := []
	for r in p.rows:
		if not has_null(r):
			full.append(r)
	var ymax := 1.0
	if p.type == "막대":
		var sums := {}
		for r in full:
			sums[r[0]] = sums.get(r[0], 0.0) + float(r[1])
		for k in sums:
			ymax = maxf(ymax, sums[k])
	else:
		for r in full:
			ymax = maxf(ymax, float(r[1]))
	ymax *= 1.15
	if p.type == "산점도":
		var xmin := INF
		var xmax := -INF
		var ymin := INF
		for r in full:
			xmin = minf(xmin, float(r[0]))
			xmax = maxf(xmax, float(r[0]))
			ymin = minf(ymin, float(r[1]))
		for r in data:
			var c := Vector2(area.position.x + 14 + (float(r[0]) - xmin) / maxf(xmax - xmin, 1.0) * (area.size.x - 28), area.end.y - 10 - (float(r[1]) - ymin) / maxf(ymax / 1.15 - ymin, 1.0) * (area.size.y - 26))
			_cv.draw_circle(c, 6, BLUE)
		return
	var slots: int = full.size() if p.type == "선" else maxi(data.size(), 3)
	if p.type == "막대":
		var cats := {}
		for r in full:
			cats[r[0]] = true
		slots = cats.size()
	var slot: float = area.size.x / slots
	var pts := PackedVector2Array()
	for i in data.size():
		var h: float = float(data[i][1]) / ymax * (area.size.y - 24)
		var cx: float = area.position.x + slot * (i + 0.5)
		var top: float = area.end.y - 14 - h
		if p.type == "막대":
			_cv.draw_rect(Rect2(cx - slot * 0.3, top, slot * 0.6, h), BLUE)
		else:
			pts.append(Vector2(cx, top))
			_cv.draw_circle(Vector2(cx, top), 5, BLUE)
		text(Vector2(cx, area.end.y - 2), str(data[i][0]).right(5), 11, INK, true)
		text(Vector2(cx, top - 3), display(data[i][1]), 11, INK, true)
	if pts.size() > 1:
		_cv.draw_polyline(pts, BLUE, 3)


func _process(_delta: float) -> void:
	# 들고 있는 물건이 로봇을 따라다니고, 가까운 자리가 노랗게 바뀌도록 매 프레임 다시 그린다
	if board != null:
		board.queue_redraw()

## 실수 뒤 노란 화살표: 다음에 집을 것 또는 넣을 곳
func next_key() -> String:
	if done:
		return ""
	var p: Dictionary = problems()[problem]
	match activity:
		"profile":
			if state.held != "":
				for c in PROFILE_TARGETS:
					if not state.tags.has(c) and p.answer[c] == state.held:
						return "put:" + c
				return ""
			for c in PROFILE_TARGETS:
				if not state.tags.has(c):
					return "take:" + p.answer[c]
		"clean":
			return "take" if state.held.is_empty() else "put:" + clean_dest(state.held)
		"stats":
			var held: Dictionary = state.held
			if state.phase == "sort":
				if held.is_empty():
					return "tray"
				return "exclude" if held.v == null else "rail:%d" % sorted_nums(p.values).find(held.v)
			if state.phase == "answer":
				if held.is_empty():
					for f in p.fields:
						if not state.ans.has(f):
							for j in p.choices.size():
								if absf(float(p.choices[j]) - stat(f, p.values)) < 0.01:
									return "shelf:%d" % j
					return ""
				for f in p.fields:
					if not state.ans.has(f) and absf(float(held.v) - stat(f, p.values)) < 0.01:
						return "ped:" + f
				return ""
			return "claim:%d" % p.answer if held.is_empty() else "npc"
		"chart":
			var held: Dictionary = state.held
			if state.phase == "claim":
				return "claim:%d" % p.answer if held.is_empty() else "question"
			if held.is_empty():
				var left := chart_left(p)
				if p.type == "선":
					left.sort_custom(func(a, b): return str(p.rows[a][0]) < str(p.rows[b][0]))
				return "card:%d" % left[0] if not left.is_empty() else ""
			if has_null(p.rows[held.i]):
				return "nullbox"
			return "easel:%d" % CHART_TYPES.find(p.type)
	return ""
