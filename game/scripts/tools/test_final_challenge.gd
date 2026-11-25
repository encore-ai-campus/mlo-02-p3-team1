extends SceneTree
## 최종 도전(CHALLENGE01_CodeBot — 4대 분야 8개 시나리오) 헤드리스 검증 테스트.

const Levels = preload("res://scripts/minigames/final_challenge_levels.gd")
const StageScript = preload("res://scripts/minigames/final_challenge_stage.gd")
const VM = preload("res://scripts/minigames/python_mini_vm.gd")

var checks := 0
var failures := 0

func _check(cond: bool, msg: String) -> void:
	checks += 1
	if not cond:
		failures += 1
		printerr("[FAIL] ", msg)
	else:
		print("[OK] ", msg)

func _initialize() -> void:
	# 1. 전 8개 레벨 정답 통과 테스트
	for i in Levels.LEVELS.size():
		var lv: Dictionary = Levels.LEVELS[i]
		var answers := {}
		for b in lv.blanks:
			answers[int(b.id)] = str(b.answer)
		var res := StageScript.simulate_level(i, answers)
		_check(res.vm.ok, "%s VM execution ok (err=%s)" % [lv.id, res.vm.error])
		_check(res.goal.ok, "%s goal achieved (%s)" % [lv.id, res.goal.reason])
		_check(res.cleared, "%s cleared" % lv.id)

	# 2. 빈칸 누락 시 오류 감지
	var empty_res := StageScript.simulate_level(0, {0: "", 1: "output(pop())"})
	_check(not empty_res.vm.ok and not empty_res.cleared, "Empty blank rejected cleanly")

	# 3. Lv2 큐 미션에 스택(push/pop) 사용 시 실패 판정
	var queue_wrong := StageScript.simulate_level(1, {0: "push(ticket)", 1: "output(pop())"})
	_check(not queue_wrong.cleared, "LV2_DS_QUEUE rejects LIFO stack when FIFO queue is required")

	# 4. Lv4 이진 탐색에서 값(val) 보고 시 실패 판정 & 이진 탐색 3회 이내 탐색 검증
	var bsearch_val := StageScript.simulate_level(3, {0: "(low + high) // 2", 1: "found(val)"})
	_check(not bsearch_val.cleared, "LV4_ALGO_BSEARCH rejects reporting value instead of index")

	# 5. Lv5 SQL 단일 따옴표 + >79 대체 정답 통과 (NULL 안전)
	var alt_sql := StageScript.simulate_level(4, {0: "dept(i) == '개발'", 1: "score(i) > 79", 2: "select_row(i)"})
	_check(alt_sql.cleared, "LV5_SQL_WHERE alternative single-quote & >79 passes (NULL safe)")

	# 6. Lv8 데이터 평균에서 전체 5로 나눴을 때(10) 오답 안내 확인
	var wrong_mean := StageScript.simulate_level(7, {0: "v < 80", 1: "report_mean(total // 5)"})
	_check(wrong_mean.vm.ok and not wrong_mean.cleared, "LV8_DATA_STAT catches dividing by total 5 instead of valid cnt")

	# 7. 무한 루프 보호 테스트
	var host := StageScript.SimHost.new(Levels.LEVELS[0])
	var inf_res := VM.execute("while True:\n    get(0)", host, 30)
	_check(not inf_res.ok and inf_res.error.contains("최대 실행 횟수"), "Infinite loop safely halted")

	print("FINAL_CHALLENGE_TEST_DONE checks=%d failures=%d" % [checks, failures])
	quit(1 if failures > 0 else 0)
