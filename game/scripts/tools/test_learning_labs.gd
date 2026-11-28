extends SceneTree
## 클릭형 실습 14종과 메뉴를 검사한다: 정상 풀이, 대표 오답, 경계값, 되돌리기, 메뉴 구성.
## 실행: Godot --headless --path . --script res://scripts/tools/test_learning_labs.gd

const Catalog = preload("res://scripts/learning_catalog.gd")
var failures := 0
var checks := 0
var game

func check(value: bool, message: String) -> void:
	checks += 1
	if not value:
		failures += 1
		print("FAIL ", message)

func _init() -> void:
	call_deferred("run")

func open(scene: String) -> void:
	game = (load("res://scenes/stages/%s.tscn" % scene) as PackedScene).instantiate()
	root.add_child(game)
	game.set("fast_flow", true)
	game.hud.dialogue_skip()

func close() -> void:
	game.free()

func level(n: int) -> void:
	game.start_level(n)
	game.hud.dialogue_skip()

func press(keys: Array) -> void:
	for k in keys:
		game.on_button(k)

func expect_wrong(keys: Array, message: String) -> void:
	var before: int = game.mistakes
	press(keys)
	check(game.mistakes > before, message + " (오답으로 처리돼야 함)")

func run() -> void:
	MiniGameBase.progress_saving = false
	var nm = root.get_node_or_null("NetworkManager")
	if nm:
		nm.auto_send_enabled = false
	create_timer(300).timeout.connect(func(): print("TIMEOUT"); quit(1))
	test_catalog()
	test_tree()
	test_graph()
	test_search()
	test_sort()
	test_divide()
	test_shortest()
	test_profile()
	test_clean()
	test_stats()
	test_chart()
	await test_world_terminals()
	print("LEARNING_LABS_TEST_DONE checks=%d failures=%d" % [checks, failures])
	quit(1 if failures else 0)

func test_world_terminals() -> void:
	var world = (load("res://scenes/NodeverseWorld.tscn") as PackedScene).instantiate()
	root.add_child(world)
	await world.world_built
	world._set_game_state(world.GameState.PLAYING)
	current_scene = world
	var seen := {}
	for terminal in world.computer_terminals:
		world.player.teleport_to(terminal.global_position + terminal.global_basis.z * 1.6)
		var camera = world.player.cam
		world.player.cam = null
		await world._open_computer_game()
		world.player.cam = camera
		var menu = current_scene
		var zone: String = terminal.get_meta("quiz_zone", "DS")
		seen[zone] = true
		check(menu != world and menu.get_script().resource_path == "res://scripts/main_menu.gd", "컴퓨터에서 메뉴 열기")
		check(Catalog.selected_category == zone and Catalog.CATEGORIES.has(zone), "분야 탭 연결 " + zone)
		check(not world.is_quiz_open, "예전 퀴즈가 열리면 안 됨")
		await process_frame
		await process_frame
		check(menu._buttons.filter(func(b): return str(b[1]).begins_with("category:")).is_empty(), "메뉴에 다른 분야 탭이 없어야 함")
		var other_game: Array = Catalog.GAMES.filter(func(g): return g[3] != zone)
		check(menu._buttons.filter(func(b): return other_game.any(func(g): return g[4] == str(b[1]))).is_empty(), "다른 분야 게임이 보이면 안 됨 " + zone)
		menu._go_back_to_world()
		check(current_scene == world, "월드 복귀")
		await process_frame
	check(seen.size() == 4, "네 분야 컴퓨터, 실제 %d" % seen.size())
	var shrine: Node3D = world._challenge_shrine
	world.player.teleport_to(shrine.global_position + Vector3(0.0, 0.0, 3.4))
	world._on_interact()
	var challenge := current_scene
	check(challenge.scene_file_path == "res://scenes/stages/CHALLENGE01_CodeBot.tscn", "판테온에서 최종 도전 진입")
	if challenge != world:
		challenge.call("_exit_to_world")
		check(current_scene == world, "최종 도전에서 월드 복귀")
	world.queue_free()
	await process_frame
	print("TERMINAL_ROUTES ok ", seen.keys())

func test_catalog() -> void:
	var ids := {}
	var plan := {}
	for g in Catalog.GAMES:
		check(not ids.has(g[0]), "중복 ID " + g[0])
		ids[g[0]] = true
		if g[7] != "보너스":
			plan[g[7]] = true
		check(ResourceLoader.exists("res://scenes/stages/%s.tscn" % g[4]), "씬 없음 " + g[4])
		var folder: String = g[6]
		check(ResourceLoader.exists("res://textures/stages/%s/bg_game.png" % folder), "배경 없음 " + folder)
	check(plan.size() == 23, "기획 게임 23개여야 함, 실제 %d" % plan.size())
	check(Catalog.CATEGORIES.size() == 5 and Catalog.CATEGORIES.has_all(["DS", "ALGO", "SQL", "DATA", "CHALLENGE"]), "학습 4개 분야와 종합 도전")
	for game in Catalog.games_for("CHALLENGE"):
		check(ResourceLoader.exists("res://scenes/stages/%s.tscn" % game[4]), "종합 도전 씬 없음 " + game[4])
	check(Catalog.games_for("DS").size() == 10, "자료구조 9+보너스")
	check(Catalog.games_for("ALGO").size() == 6, "알고리즘 6")
	check(Catalog.games_for("SQL").size() == 4, "SQL 4")
	check(Catalog.games_for("DATA").size() == 4, "데이터 4")
	for keep in ["ST01", "ST02", "ST03", "ST04", "ST05", "ST06", "ST07", "ST08", "ST09", "ST10", "DS09", "ALG01", "ALG02", "SQL01", "DATA01"]:
		check(ids.has(keep), "기존 저장 ID 유지 " + keep)
	var tree: Array = Catalog.GAMES.filter(func(g): return g[0] == "DS09")[0]
	var graph: Array = Catalog.GAMES.filter(func(g): return g[0] == "DS10")[0]
	check(tree[6] == "ST06" and graph[6] == "ST09", "트리·그래프는 ST06·ST09 배경")
	print("CATALOG ok games=", Catalog.GAMES.size())

func test_tree() -> void:
	open("DS09_TreeStructure")
	check(game.level_count == 3, "트리 3레벨")
	press(["A", "A", "left"])
	check(game.mistakes == 1, "자기 연결 거부")
	game.state.parent = ""
	game.state.child = ""
	press(["A", "B", "left", "A", "C", "left"])
	check(game.mistakes == 2, "슬롯 중복 거부")
	game.state.parent = ""
	game.state.child = ""
	press(["A", "C", "right", "check"])
	check(game.level_done, "트리 L1 완료")
	level(1)
	press(["B", "A", "left"])
	check(game.mistakes == 1, "루트를 자식으로 거부")
	game.state.parent = ""
	game.state.child = ""
	press(["A", "B", "left", "C", "B", "left"])
	check(game.mistakes == 2, "중복 부모 거부")
	game.state.parent = ""
	game.state.child = ""
	press(["A", "C", "right", "B", "D", "left", "C", "E", "right", "check"])
	check(game.level_done, "트리 L2 완료")
	level(2)
	press(["C", "D", "unlink", "B", "C", "unlink"])
	check(game.state.edges == {"A": ["B", null]}, "연결 해제")
	press(["D", "A", "left"])
	check(game.mistakes == 1, "루트 거부2")
	game.state.parent = ""
	game.state.child = ""
	press(["B", "D", "left"])
	press(["D", "B", "left"])
	check(game.mistakes == 2, "순환 거부")
	game.state.parent = ""
	game.state.child = ""
	game.undo()
	check(game.state.edges == {"A": ["B", null]}, "되돌리기 복원")
	press(["B", "D", "left", "A", "C", "right", "B", "E", "right", "check"])
	check(game.level_done, "트리 L3 복원 완료")
	close()
	print("TREE ok")

func test_graph() -> void:
	open("DS10_GraphBuild")
	press(["A", "A", "add"])
	check(game.mistakes == 1, "자기 간선 거부")
	press(["A", "B", "add", "B", "A", "add"])
	check(game.mistakes == 2, "무방향 평행 간선 거부")
	press(["B", "D", "add", "check"])
	check(game.mistakes == 3 and not game.level_done, "미완성 제출")
	press(["C", "A", "add", "D", "C", "add", "check"])
	check(game.level_done, "그래프 L1 완료")
	level(1)
	press(["B", "A", "add", "check"])
	check(game.mistakes == 1, "방향 반대 안내")
	press(["B", "A", "del", "A", "B", "add", "B", "C", "add", "C", "A", "add", "D", "A", "add"])
	check(game.reachable("D") == ["A", "B", "C"], "방향 도달 계산")
	check(game.reachable("A").has("C") and not game.reachable("A").has("D"), "역방향 도달 불가")
	press(["check"])
	check(game.level_done, "순환 포함 L2 완료")
	level(2)
	press(["C", "B", "del"])
	game.state.cost = 3
	press(["A", "B", "add"])
	check(game.state.edges["A>B"] == 3, "비용 수정")
	press(["cost-", "B", "C", "add"])
	game.state.cost = 4
	press(["C", "A", "add"])
	game.state.cost = 1
	press(["D", "A", "add", "check"])
	check(game.level_done, "단절 정점 포함 L3 완료")
	close()
	print("GRAPH ok")

func test_search() -> void:
	open("ALG02_Search")
	expect_wrong(["2"], "선형은 왼쪽부터")
	press(["0", "1", "2", "3"])
	check(game.problem == 1, "선형 찾기 후 다음 문제")
	press(["0", "1", "2"])
	check(game.level_done, "선형 끝까지 없음")
	level(1)
	expect_wrong(["0"], "중앙이 아닌 칸 거부")
	press(["3", "5", "4"])
	check(game.problem == 1, "16은 3→5→4")
	press(["0"])
	check(game.level_done, "한 원소 탐색")
	level(2)
	press(["3", "5", "4"])
	check(game.problem == 1, "없는 값 종료")
	press(["2"])
	check(game.problem == 2, "중복 값 찾기")
	expect_wrong(["pick:binary"], "미정렬 이진 탐색 차단")
	press(["pick:linear", "0", "1", "2"])
	check(game.problem == 3, "방법 선택 후 선형")
	press(["none"])
	check(game.level_done, "빈 배열 없음 선언")
	close()
	print("SEARCH ok")

func vals() -> Array:
	return game.state.a.map(func(c): return c[0])

func test_sort() -> void:
	open("ALG01_Sorting")
	expect_wrong(["3"], "비인접 교환 거부")
	expect_wrong(["keep"], "교환해야 할 때 유지 거부")
	var guard := 0
	while game.problem == 0 and guard < 30:
		guard += 1
		var a: Array = vals()
		var j: int = game.state.j
		press(["swap" if a[j] > a[j + 1] else "keep"])
	check(game.problem == 1, "버블 첫 문제 완료")
	var moves_before: int = game.state.cmp
	press(["keep", "keep"])
	check(game.level_done and moves_before == 0, "정렬된 입력은 한 패스로 종료")
	level(1)
	expect_wrong(["0"], "최솟값 아닌 카드 거부")
	press(["4", "1", "2"])
	press(["3"])
	check(game.level_done, "선택 정렬 완료")
	check(vals() == [1, 3, 3, 6, 7], "선택 정렬 결과와 중복 보존")
	level(2)
	expect_wrong(["2"], "다음 key 아닌 카드 거부")
	press(["1"])
	expect_wrong(["place"], "큰 값을 밀지 않고 놓기 거부")
	guard = 0
	while not game.level_done and guard < 200:
		guard += 1
		if game.state.phase == "lift":
			press([str(game.state.i)])
		else:
			var a: Array = vals()
			var j: int = game.state.hole - 1
			press(["shift" if j >= 0 and a[j] > game.state.key[0] else "place"])
	check(game.level_done and vals() == [-2, 0, 1, 3, 5, 9], "삽입 정렬 음수 포함")
	close()
	print("SORT ok")

func test_divide() -> void:
	open("ALG03_DivideSort")
	press(["run:0"])
	check(game.state.runs.size() == 2, "한 번 분할")
	press(["run:0", "run:2"])
	check(game.problem == 1, "4원소 모두 분할")
	press(["run:0", "run:0"])
	expect_wrong(["run:0"], "한 원소 분할 거부")
	var guard := 0
	while not game.level_done and guard < 20:
		guard += 1
		for i in game.state.runs.size():
			if game.state.runs[i].size() > 1:
				press(["run:%d" % i])
				break
	check(game.level_done, "홀수 길이 분할")
	level(1)
	check(game.state.plan.size() == 3, "4원소 병합 3번")
	guard = 0
	while not game.level_done and guard < 100:
		guard += 1
		var m: Dictionary = game.state.plan[game.state.m]
		var l: int = game.state.l
		var r: int = game.state.r
		var left_ok: bool = l < m.left.size() and (r >= m.right.size() or m.left[l][0] <= m.right[r][0])
		if guard == 1:
			expect_wrong(["right" if left_ok else "left"], "병합 순서 오류 거부")
		press(["left" if left_ok else "right"])
	check(game.level_done, "병합 L2 완료")
	level(2)
	var pivot = game.state.segs[0].items.back()[0]
	check(pivot == 4, "첫 pivot은 마지막 값")
	expect_wrong(["lt"], "6은 pivot보다 큼")
	guard = 0
	while not game.level_done and guard < 200:
		guard += 1
		var s: int = game.current_segment()
		var items: Array = game.state.segs[s].items
		var p = items.back()[0]
		var c = items[game.state.k][0]
		press(["eq" if c == p else ("lt" if c < p else "gt")])
	check(game.level_done, "퀵 정렬 완료, 모두 같은 값 포함")
	close()
	print("DIVIDE ok")

func solve_path() -> void:
	var p: Dictionary = game.problems()[game.problem]
	var pid: int = game.problem
	var guard := 0
	while not game.level_done and game.problem == pid and guard < 200:
		guard += 1
		match game.state.phase:
			"negative":
				press(["unusable"])
			"select":
				var low: int = game.INF
				var best := ""
				var names: Array = p.pos.keys()
				names.sort()
				for v in names:
					if not game.state.settled.has(v) and game.state.dist[v] < low:
						low = game.state.dist[v]
						best = v
				press(["unreachable" if best == "" else best])
			"relax":
				var n: Array = game.state.queue[0]
				press(["update" if game.state.dist[game.state.cur] + n[1] < game.state.dist[n[0]] else "keep"])
			"path":
				var from: String = game.state.path.back()
				var moved := false
				for e in p.edges:
					if e[0] == from and game.state.settled.has(e[1]) and game.state.dist[from] + e[2] == game.state.dist[e[1]] and game.on_tight_route(p, e[1]):
						press([e[1]])
						moved = true
						break
				if not moved:
					return

func test_shortest() -> void:
	open("ALG04_ShortestPath")
	expect_wrong(["B"], "미확정 최소 아닌 정점 거부")
	press(["A"])
	expect_wrong(["keep"], "갱신해야 할 때 유지 거부")
	solve_path()
	check(game.level_done, "최단 경로 L1")
	check(game.state.dist["D"] == 4, "A→C→B→D 비용 4")
	check(game.state.path == ["A", "C", "B", "D"], "경로 복원")
	level(1)
	solve_path()
	check(game.level_done and game.state.dist["E"] == 7, "우회 경로 비용 7")
	level(2)
	solve_path()
	check(game.problem == 1 and game.mistakes == 0, "동률 최단 경로")
	var p: Dictionary = game.problems()[1]
	press(["A", "update"])
	expect_wrong(["unreachable"], "남은 정점이 있을 때 도달 불가 거부")
	game.mistakes = 0
	solve_path()
	check(game.problem == 2, "도달 불가 판정")
	press(["A"])
	check(game.problem == 3, "시작=목적지 비용 0")
	expect_wrong(["A"], "음수 지도 실행 거부")
	press(["unusable"])
	check(game.level_done, "음수 간선 사용 불가")
	check(p.goal == "D", "데이터 유지")
	close()
	print("SHORTEST ok")

func type_field(key: String, text: String) -> void:
	press(["field:" + key])
	for ch in text:
		press(["key:" + ch])

func pick(key: String, n: int) -> void:
	for i in n:
		press(["pick:" + key])

func test_profile() -> void:
	open("DATA02_Profile")
	var source := str(game.PROFILE_ROWS)
	press(["put:age"])
	check(game.mistakes == 0 and game.state.tags.is_empty(), "빈손으로 붙이기는 안내만")
	expect_wrong(["take:숫자", "put:zip"], "우편번호에 숫자 꼬리표는 오답")
	check(game.state.held == "", "틀린 꼬리표는 선반으로 돌아감")
	press(["take:숫자", "put:age", "take:문자", "put:zip", "take:날짜", "put:joined"])
	check(not game.level_done, "세 열만 붙이면 아직 미완료")
	press(["take:숫자", "put:visits"])
	check(game.level_done, "자료형 꼬리표 완료")
	level(1)
	expect_wrong(["take:결측 있음", "put:visits"], "0을 결측으로 보면 오답")
	press(["take:결측 있음", "put:age", "take:결측 없음", "put:zip", "take:결측 없음", "put:joined", "take:결측 없음", "put:visits"])
	check(game.level_done, "결측 꼬리표 완료")
	level(2)
	expect_wrong(["take:형식 섞임", "put:age"], "NULL을 형식 문제로 보면 오답")
	press(["take:형식 OK", "put:age", "take:형식 OK", "put:zip", "take:형식 섞임", "put:joined", "take:형식 OK", "put:visits"])
	check(game.level_done, "형식 꼬리표 완료")
	check(str(game.PROFILE_ROWS) == source, "원본 무변경")
	close()
	print("PROFILE ok")

func kept_ids() -> Array:
	return game.state.kept.map(func(r): return r[0])

func test_clean() -> void:
	open("DATA01_Explore")
	press(["put:keep"])
	check(game.mistakes == 0 and game.state.kept.is_empty(), "빈손으로 넣기는 안내만")
	press(["take"])
	check(game.state.held[0] == 1, "선반 맨 위 카드부터 집음")
	expect_wrong(["put:drop"], "멀쩡한 카드를 버리면 오답")
	check(not game.state.held.is_empty(), "틀려도 카드는 손에 남음")
	press(["put:keep", "take"])
	expect_wrong(["put:keep"], "빈 값 카드를 투입구에 넣으면 오답")
	press(["put:drop", "take", "put:keep", "take", "put:drop", "take"])
	expect_wrong(["put:drop"], "0을 빈 값으로 보면 오답")
	press(["put:keep"])
	check(game.level_done and kept_ids() == [1, 3, 5], "DA-02 L1: 0 유지")
	level(1)
	press(["take", "put:keep", "take"])
	expect_wrong(["put:keep"], "group+value 중복을 남기면 오답")
	press(["put:dup", "take", "put:keep", "take", "put:keep", "take", "put:dup", "take", "put:drop"])
	check(game.level_done and kept_ids() == [1, 3, 4], "DA-02 L2")
	level(2)
	press(["take"])
	game.undo()
	check(game.state.held.is_empty() and game.state.queue.size() == 7, "되돌리면 카드가 선반으로")
	press(["take"])
	expect_wrong(["put:keep"], "모양이 틀린 카드는 수리가 먼저")
	press(["put:fix"])
	check(game.state.held[1] == "A" and game.state.held[2] == "1000" and game.state.held[3] == "2026-01-05", "수리하면 공백·쉼표·슬래시 정리")
	press(["put:keep", "take"])
	expect_wrong(["put:fix"], "고칠 곳 없는 카드 수리는 오답")
	press(["put:dup", "take"])
	expect_wrong(["put:fix"], "abc는 고칠 수 없음")
	press(["put:drop", "take", "put:drop", "take", "put:keep", "take", "put:fix", "put:dup", "take", "put:keep"])
	check(game.level_done and kept_ids() == [1, 5, 7], "DA-02 L3: 3행")
	close()
	print("CLEAN ok")

func sort_all() -> void:
	var p: Dictionary = game.problems()[game.problem]
	var s: Array = game.sorted_nums(p.values)
	while not game.state.tray.is_empty():
		press(["tray"])
		var v = game.state.held.v
		press(["exclude" if v == null else "rail:%d" % s.find(v)])

func put_answer(f: String, v) -> void:
	var p: Dictionary = game.problems()[game.problem]
	press(["shelf:%d" % p.choices.find(v), "ped:" + f])

func test_stats() -> void:
	open("DATA03_Stats")
	press(["tray"])
	check(game.state.held.v == 4, "쟁반 첫 블록")
	expect_wrong(["rail:0"], "4는 첫째 칸이 아님")
	press(["rail:1"])
	check(game.state.rail[1] == 4, "4 → 둘째 칸")
	sort_all()
	check(game.state.phase == "answer" and game.state.rail.slice(0, 4) == [2, 4, 6, 8], "정렬 완료 후 답 단계")
	press(["shelf:0"])
	expect_wrong(["ped:range"], "5는 범위가 아님")
	check(game.state.held.is_empty(), "틀린 답 블록은 선반으로")
	put_answer("mean", 5)
	put_answer("median", 5)
	put_answer("range", 6)
	check(game.level_done, "DA-03 L1")
	level(1)
	sort_all()
	put_answer("median", 5)
	check(game.problem == 1, "홀수 중앙값")
	sort_all()
	press(["shelf:%d" % game.problems()[1].choices.find(12)])
	expect_wrong(["ped:median"], "짝수 개는 가운데 두 값의 평균")
	put_answer("median", 13)
	check(game.problem == 2, "짝수 중앙값")
	press(["tray", "rail:0", "tray"])
	expect_wrong(["rail:1"], "NULL은 레일에 못 꽂음")
	press(["exclude", "tray", "rail:1"])
	press(["shelf:%d" % game.problems()[2].choices.find(4)])
	expect_wrong(["ped:mean"], "NULL을 개수에 넣으면 오답")
	put_answer("mean", 6)
	check(game.level_done, "NULL 제외 평균")
	level(2)
	sort_all()
	put_answer("mean", 34)
	put_answer("median", 13)
	check(game.state.phase == "claim", "결론 단계")
	expect_wrong(["claim:1", "npc"], "이상치 삭제 결론 거부")
	press(["claim:0", "npc"])
	check(game.problem == 1, "이상치 비교")
	sort_all()
	put_answer("range", 20)
	expect_wrong(["claim:1", "npc"], "같은 평균 같은 분포 거부")
	press(["claim:0", "npc"])
	check(game.problem == 2 and game.state.phase == "claim", "빈 집단은 바로 결론")
	expect_wrong(["claim:1", "npc"], "빈 집단 평균 0 거부")
	press(["claim:0", "npc"])
	check(game.level_done, "DA-03 L3")
	close()
	print("STATS ok")

func test_chart() -> void:
	open("DATA04_Chart")
	press(["card:0"])
	expect_wrong(["easel:1"], "범주 비교에 선 차트는 오답")
	press(["easel:0"])
	for i in [1, 2, 3, 4]:
		press(["card:%d" % i, "easel:0"])
	var d: Array = game.chart_series(game.problems()[0])
	check(d.size() == 3 and d[1][0] == "공책" and d[1][1] == 55.0, "같은 제품은 막대에 쌓여 합계")
	check(game.state.phase == "claim", "카드를 다 꽂으면 결론 단계")
	expect_wrong(["claim:2", "question"], "원인 단정 거부")
	press(["claim:0", "question"])
	check(game.level_done, "DA-04 L1")
	level(1)
	press(["card:0"])
	expect_wrong(["easel:1"], "3월부터 꽂으면 시간 순서 오답")
	press(["easel:1"])
	check(game.state.held.is_empty() == false, "틀리면 카드는 손에 남음")
	game.state.held = {}
	game.state.taken.erase(0)
	press(["card:1", "easel:1", "card:2", "easel:1", "card:0", "easel:1"])
	var months: Array = game.chart_series(game.problems()[0]).map(func(r): return r[0])
	check(months == ["2026-01", "2026-02", "2026-03"], "선은 시간순으로 이어짐")
	press(["claim:0", "question"])
	check(game.level_done, "DA-04 L2")
	level(2)
	press(["card:3"])
	expect_wrong(["easel:2"], "빈 값 카드는 그릴 수 없음")
	press(["nullbox", "card:0"])
	expect_wrong(["nullbox"], "값이 다 있는 카드는 빈 값 상자 아님")
	press(["easel:2", "card:1", "easel:2", "card:2", "easel:2", "card:4", "easel:2", "card:5", "nullbox"])
	check(game.chart_series(game.problems()[0]).size() == 4 and game.state.phase == "claim", "NULL 카드 제외하고 점 4개")
	expect_wrong(["claim:1", "question"], "상관을 인과로 해석 거부")
	press(["claim:0", "question"])
	check(game.level_done, "DA-04 L3")
	close()
	print("CHART ok")

