class_name FinalChallengeLevels
extends RefCounted
## 최종 도전(CHALLENGE01_CodeBot) 시나리오 데이터 — Nodeverse 4개 분야 8대 미니게임 Python 코드 자동화 챌린지.
## 시나리오를 추가·수정할 때는 LEVELS 배열만 편집하면 상단 레벨 탭과 스테이지 UI에 즉시 반영된다.

const STAGE_ID := "ST10"
const STAGE_TITLE := "최종 도전 · 로봇 코드 자동화"

const LEVELS := [
	# 1. 자료구조 (ST01 배열 + ST03 스택)
	{
		"id": "LV1_DS_STACK",
		"domain": "자료구조",
		"mode": "stack_reverse",
		"title": "Lv 1. [자료구조] 배열 & 스택 역순 복구",
		"goal": "보관함 [10, 20, 30, 40]을 스택(LIFO)으로 역순 [40, 30, 20, 10] 복구하세요",
		"brief": "참고 미니게임: ST01(배열) · ST03(스택)\n로봇이 0~3번 보관함 상자를 읽어 스택 탑에 쌓은 뒤(push), 맨 위부터 꺼내(pop) 복구 작업대에 역순 배치하도록 완성하세요.",
		"slots": [10, 20, 30, 40],
		"target": [40, 30, 20, 10],
		"code_lines": [
			"# 1) 보관함 0~3번 상자를 스택(LIFO)에 순서대로 쌓기",
			"for i in range(4):",
			"    val = get(i)",
			"    {{0}}",
			"# 2) 스택 맨 위에서 꺼내(pop) 복구 작업대에 배치하기",
			"for i in range(4):",
			"    {{1}}",
		],
		"blanks": [
			{"id": 0, "hint": "스택에 값 쌓기", "answer": "push(val)", "width": 150},
			{"id": 1, "hint": "스택에서 꺼내 배치", "answer": "output(pop())", "width": 175},
		],
		"choices": ["push(val)", "output(pop())", "output(val)", "pop()", "enqueue(val)"],
		"api_help": "get(i) i번 칸 읽기 · push(v) 스택 쌓기 · pop() 스택 꺼내기 · output(v) 작업대 배치",
		"hints": [
			"스택(Stack)은 나중에 넣은 것이 먼저 나오는 후입선출(LIFO) 구조예요.",
			"push(val)로 10→20→30→40을 쌓으면, pop()할 때 40→30→20→10 순으로 꺼내집니다.",
			"정답 예시: push(val) / output(pop())",
		],
		"max_steps": 160,
	},

	# 2. 자료구조 (ST04 큐)
	{
		"id": "LV2_DS_QUEUE",
		"domain": "자료구조",
		"mode": "queue_fifo",
		"title": "Lv 2. [자료구조] 큐(FIFO) 민원 접수 순서 처리",
		"goal": "대기 민원 [101, 102, 103, 104]를 큐(FIFO)에 넣어 접수 순서대로 처리하세요",
		"brief": "참고 미니게임: ST04(접수 순서 안내소 · 큐)\n먼저 온 요청을 먼저 처리하는 선입선출(FIFO) 벨트입니다! 대기열에서 큐에 넣은(enqueue) 순서 그대로 꺼내(dequeue) 창구로 보내세요.",
		"slots": [101, 102, 103, 104],
		"target": [101, 102, 103, 104],
		"code_lines": [
			"# 1) 접수 번호 0~3번을 큐 벨트 뒤쪽(REAR)에 줄 세우기",
			"for i in range(4):",
			"    ticket = get(i)",
			"    {{0}}",
			"# 2) 큐 앞쪽(FRONT)부터 순서대로 꺼내 창구 배정하기",
			"for i in range(4):",
			"    {{1}}",
		],
		"blanks": [
			{"id": 0, "hint": "큐에 줄 세우기", "answer": "enqueue(ticket)", "width": 180},
			{"id": 1, "hint": "큐에서 꺼내 처리", "answer": "output(dequeue())", "width": 195},
		],
		"choices": ["enqueue(ticket)", "output(dequeue())", "push(ticket)", "output(pop())", "dequeue()"],
		"api_help": "get(i) 접수표 읽기 · enqueue(v) 큐 넣기 · dequeue() 큐 앞쪽 꺼내기 · output(v) 창구 처리",
		"hints": [
			"큐(Queue)는 먼저 들어간 데이터가 먼저 나오는 선입선출(FIFO) 구조예요.",
			"스택(push/pop)을 쓰면 순서가 뒤집히니, 큐 전용 명령어 enqueue / dequeue 를 사용하세요.",
			"정답 예시: enqueue(ticket) / output(dequeue())",
		],
		"max_steps": 160,
	},

	# 3. 알고리즘 (ALG01 기본 정렬)
	{
		"id": "LV3_ALGO_SORT",
		"domain": "알고리즘",
		"mode": "bubble_sort",
		"title": "Lv 3. [알고리즘] 작업대 오름차순 버블 정렬",
		"goal": "작업대 [40, 15, 35, 10, 25]를 오름차순 [10, 15, 25, 35, 40]으로 정렬하세요",
		"brief": "참고 미니게임: ALG01(순서 맞춤 작업대 · 버블 정렬)\n인접한 두 칸(j와 j + 1)을 비교해 왼쪽 값이 더 크면 서로 교환(swap)하여 가장 큰 값부터 오른쪽 끝에 확정하세요.",
		"slots": [40, 15, 35, 10, 25],
		"target": [10, 15, 25, 35, 40],
		"code_lines": [
			"# 인접한 두 칸을 비교해 큰 값을 오른쪽으로 보내는 버블 정렬",
			"for p in range(4):",
			"    for j in range(4 - p):",
			"        if {{0}}:",
			"            {{1}}",
		],
		"blanks": [
			{"id": 0, "hint": "왼쪽이 더 큰지 비교", "answer": "get(j) > get(j + 1)", "width": 215},
			{"id": 1, "hint": "두 칸 상자 교환", "answer": "swap(j, j + 1)", "width": 175},
		],
		"choices": ["get(j) > get(j + 1)", "get(j) < get(j + 1)", "swap(j, j + 1)", "push(get(j))", "found(j)"],
		"api_help": "get(j) j번 칸 값 읽기 · swap(a, b) 두 칸의 상자 위치 교환",
		"hints": [
			"오름차순 정렬은 작은 값이 왼쪽, 큰 값이 오른쪽에 와야 해요.",
			"왼쪽 get(j)가 오른쪽 get(j + 1)보다 크면(> ) swap(j, j + 1)로 자리를 맞바꾸세요.",
			"정답 예시: get(j) > get(j + 1) / swap(j, j + 1)",
		],
		"max_steps": 220,
	},

	# 4. 알고리즘 (ALG02 이진 탐색)
	{
		"id": "LV4_ALGO_BSEARCH",
		"domain": "알고리즘",
		"mode": "binary_search",
		"title": "Lv 4. [알고리즘] 정렬된 서고 이진 탐색",
		"goal": "정렬된 서고 [5, 12, 19, 27, 34, 42, 58]에서 값 34의 위치를 이진 탐색으로 찾으세요",
		"brief": "참고 미니게임: ALG02(물건 찾기 비교실 · 이진 탐색)\n처음부터 다 뒤지지 않고 구간 [low..high]의 정중앙(mid)만 확인해 탐색 범위를 절반씩 줄여 목표값 34를 찾으세요!",
		"slots": [5, 12, 19, 27, 34, 42, 58],
		"target_val": 34,
		"target_idx": 4,
		"max_reads": 6,
		"code_lines": [
			"low = 0",
			"high = 6",
			"while low <= high:",
			"    mid = {{0}}",
			"    val = get(mid)",
			"    if val == 34:",
			"        {{1}}",
			"        break",
			"    elif val < 34:",
			"        low = mid + 1",
			"    else:",
			"        high = mid - 1",
		],
		"blanks": [
			{"id": 0, "hint": "구간의 가운데 인덱스", "answer": "(low + high) // 2", "width": 200},
			{"id": 1, "hint": "찾은 위치 보고", "answer": "found(mid)", "width": 150},
		],
		"choices": ["(low + high) // 2", "low + 1", "found(mid)", "found(val)", "swap(low, high)"],
		"api_help": "get(mid) 중앙값 확인 · found(idx) 찾은 인덱스 확정 (이진 탐색은 3번 이내 조회로 해결!)",
		"hints": [
			"정수 중앙 인덱스는 low와 high를 더한 뒤 2로 몫 나눗셈(//)을 해 구합니다.",
			"값을 찾았을 때는 값(34)이 아니라 인덱스(mid)를 found(mid)로 보고해야 합니다.",
			"정답 예시: (low + high) // 2 / found(mid)",
		],
		"max_steps": 160,
	},

	# 5. SQL (SQL01 조건 조회)
	{
		"id": "LV5_SQL_WHERE",
		"domain": "SQL",
		"mode": "sql_filter",
		"title": "Lv 5. [SQL] 개발팀 장학생(80점 이상) 조회",
		"goal": "WHERE dept = '개발' AND score >= 80 조건에 맞는 학생만 추출하세요",
		"brief": "참고 미니게임: SQL01(필요한 칸만 꺼내기 · 조건 조회)\nstudents 테이블 6행을 순회하며 부서가 '개발'이고 점수가 80점 이상인 행만 select_row(i)로 결과표에 담아 주세요.",
		"rows": [
			{"id": 1, "name": "민지", "dept": "개발", "score": 90},
			{"id": 2, "name": "준호", "dept": "디자인", "score": 55},
			{"id": 3, "name": "서연", "dept": "개발", "score": 80},
			{"id": 4, "name": "도윤", "dept": "디자인", "score": null},
			{"id": 5, "name": "하늘", "dept": "기획", "score": 70},
			{"id": 6, "name": "유진", "dept": "개발", "score": 65},
		],
		"target_ids": [1, 3],
		"code_lines": [
			"# SELECT * FROM students WHERE dept = '개발' AND score >= 80",
			"for i in range(6):",
			"    if {{0}} and {{1}}:",
			"        {{2}}",
		],
		"blanks": [
			{"id": 0, "hint": "개발 부서 조건", "answer": "dept(i) == \"개발\"", "width": 146},
			{"id": 1, "hint": "80점 이상 조건", "answer": "score(i) >= 80", "width": 136},
			{"id": 2, "hint": "조건 통과 행 추출", "answer": "select_row(i)", "width": 152},
		],
		"choices": ["dept(i) == \"개발\"", "dept(i) == \"기획\"", "score(i) >= 80", "score(i) > 80", "select_row(i)", "drop_row(i)"],
		"api_help": "dept(i) i번 행 부서 · score(i) i번 행 점수(NULL 가능) · select_row(i) 결과표 추출",
		"hints": [
			"부서 확인은 dept(i) == \"개발\" 로 비교합니다.",
			"80점 '이상'이므로 >= 80 이어야 서연(80점)도 포함됩니다. NULL 점수는 자동으로 통과하지 못해요.",
			"정답 예시: dept(i) == \"개발\" / score(i) >= 80 / select_row(i)",
		],
		"max_steps": 160,
	},

	# 6. SQL (SQL02 그룹·조건 집계)
	{
		"id": "LV6_SQL_AGG",
		"domain": "SQL",
		"mode": "sql_sum",
		"title": "Lv 6. [SQL] 서울 지역 유효 매출 합계(SUM) 집계",
		"goal": "서울 지역의 NULL이 아닌 거래 금액만 합산해 report_sum(total)으로 보고하세요",
		"brief": "참고 미니게임: SQL02(부서별 실적 보고서 · SUM 집계)\nSQL의 SUM(amount)은 NULL을 제외하고 더합니다! 서울 지역이면서 결측이 아닌 금액만 total에 누적해 보고하세요.",
		"rows": [
			{"id": 1, "dept": "A", "region": "서울", "amount": 10},
			{"id": 2, "dept": "A", "region": "부산", "amount": 20},
			{"id": 3, "dept": "B", "region": "서울", "amount": 15},
			{"id": 4, "dept": "B", "region": "서울", "amount": null},
			{"id": 5, "dept": "C", "region": "서울", "amount": 40},
			{"id": 6, "dept": "D", "region": "부산", "amount": 30},
		],
		"target_sum": 65,
		"code_lines": [
			"# SELECT SUM(amount) FROM sales WHERE region = '서울'",
			"total = 0",
			"for i in range(6):",
			"    if {{0}} and not is_null(i):",
			"        total += {{1}}",
			"{{2}}",
		],
		"blanks": [
			{"id": 0, "hint": "서울 지역 조건", "answer": "region(i) == \"서울\"", "width": 190},
			{"id": 1, "hint": "i번 행 금액 읽기", "answer": "amount(i)", "width": 140},
			{"id": 2, "hint": "최종 합계 보고", "answer": "report_sum(total)", "width": 190},
		],
		"choices": ["region(i) == \"서울\"", "region(i) == \"부산\"", "amount(i)", "report_sum(total)", "select_row(i)"],
		"api_help": "region(i) 지역 · is_null(i) 금액 NULL 여부 · amount(i) 금액 · report_sum(v) 집계 제출",
		"hints": [
			"서울 지역만 추리려면 region(i) == \"서울\" 조건을 넣으세요.",
			"각 행의 거래 금액은 amount(i)로 읽어서 total에 더하고, 반복문이 끝난 뒤 report_sum(total)을 호출합니다.",
			"정답 예시: region(i) == \"서울\" / amount(i) / report_sum(total)",
		],
		"max_steps": 180,
	},

	# 7. 데이터 탐색 (DATA01 데이터 정제)
	{
		"id": "LV7_DATA_CLEAN",
		"domain": "데이터 탐색",
		"mode": "data_clean",
		"title": "Lv 7. [데이터 탐색] 결측(NULL) & 이상치 정제",
		"goal": "결측(NULL)과 100 이상 이상치를 제거(drop)하고 정상 행만 보존(keep)하세요",
		"brief": "참고 미니게임: DATA01(기록 수리 공방 · 데이터 정제)\n관측 기록에 비어 있는 값(NULL)과 비정상 이상치(999)가 섞여 있습니다. 결측이거나 100 이상인 행은 제거하고 정상 행만 남기세요!",
		"rows": [
			{"id": 1, "group": "A", "value": 10},
			{"id": 2, "group": "B", "value": null},
			{"id": 3, "group": "A", "value": 30},
			{"id": 4, "group": "C", "value": 999},
			{"id": 5, "group": "B", "value": null},
			{"id": 6, "group": "D", "value": 20},
		],
		"target_keep_ids": [1, 3, 6],
		"target_drop_ids": [2, 4, 5],
		"code_lines": [
			"# 결측(NULL) 또는 100 이상 이상치는 제거하고 정상 행만 보존",
			"for i in range(6):",
			"    if {{0}} or {{1}}:",
			"        {{2}}",
			"    else:",
			"        keep_row(i)",
		],
		"blanks": [
			{"id": 0, "hint": "결측(NULL) 여부 확인", "answer": "is_null(i)", "width": 124},
			{"id": 1, "hint": "이상치(100 이상) 조건", "answer": "value(i) >= 100", "width": 148},
			{"id": 2, "hint": "불량 행 제거", "answer": "drop_row(i)", "width": 145},
		],
		"choices": ["is_null(i)", "value(i) >= 100", "value(i) < 100", "drop_row(i)", "keep_row(i)"],
		"api_help": "is_null(i) 결측 여부 · value(i) i번 행 값 · drop_row(i) 제거 · keep_row(i) 보존",
		"hints": [
			"결측치(NULL)인지 검사하는 함수는 is_null(i) 입니다.",
			"100 이상 이상치는 value(i) >= 100 으로 판별하고, 둘 중 하나라도 해당하면(or) drop_row(i)로 제거하세요.",
			"정답 예시: is_null(i) / value(i) >= 100 / drop_row(i)",
		],
		"max_steps": 180,
	},

	# 8. 데이터 탐색 (DATA03 대표값 실험실)
	{
		"id": "LV8_DATA_STAT",
		"domain": "데이터 탐색",
		"mode": "data_mean",
		"title": "Lv 8. [데이터 탐색] 이상치 제외 대표 평균 산출",
		"goal": "관측값 [10, 12, 14, 100, 16]에서 이상치(>=80)를 제외한 평균(13)을 보고하세요",
		"brief": "참고 미니게임: DATA03(대표값 실험실 · 이상치와 평균)\n극단적인 이상치(100) 하나 때문에 평균이 왜곡됩니다! 80 미만인 정상 데이터만 골라 합계와 개수를 세고 평균을 계산해 보고하세요.",
		"slots": [10, 12, 14, 100, 16],
		"target_mean": 13,
		"code_lines": [
			"total = 0",
			"cnt = 0",
			"for i in range(5):",
			"    v = get(i)",
			"    if {{0}}:",
			"        total += v",
			"        cnt += 1",
			"{{1}}",
		],
		"blanks": [
			{"id": 0, "hint": "정상 범위(80 미만) 조건", "answer": "v < 80", "width": 145},
			{"id": 1, "hint": "평균(합계 // 개수) 보고", "answer": "report_mean(total // cnt)", "width": 255},
		],
		"choices": ["v < 80", "v >= 80", "report_mean(total // cnt)", "report_mean(total // 5)", "push(v)"],
		"api_help": "get(i) i번 관측값 읽기 · report_mean(평균값) 산출한 대표 평균 제출",
		"hints": [
			"이상치 100을 제외하려면 v < 80 조건으로 정상 값(10, 12, 14, 16)만 더해야 해요.",
			"전체 5개가 아니라 정상 데이터 개수(cnt = 4)로 나누어야 정확한 제외 후 평균(52 // 4 = 13)이 됩니다!",
			"정답 예시: v < 80 / report_mean(total // cnt)",
		],
		"max_steps": 180,
	},
]
